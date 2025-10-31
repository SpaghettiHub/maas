#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import asyncio
from collections.abc import AsyncGenerator
import hashlib
import os
from pathlib import Path
import shutil
from unittest.mock import AsyncMock, Mock

from aiofiles.threadpool.binary import AsyncBufferedIOBase
import httpx
import pytest
from temporalio import activity
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError, CancelledError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from maascommon.enums.boot_resources import (
    BootResourceFileType,
    BootResourceType,
)
from maascommon.enums.notifications import (
    NotificationCategoryEnum,
    NotificationComponent,
)
from maascommon.workflows.bootresource import (
    CleanupOldBootResourceSetsParam,
    DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
    GetFilesToDownloadForSelectionParam,
    GetFilesToDownloadReturnValue,
    GetLocalBootResourcesParamReturnValue,
    ResourceDeleteParam,
    ResourceDownloadParam,
    ResourceIdentifier,
    SYNC_ALL_LOCAL_BOOTRESOURCES_WORKFLOW_NAME,
    SYNC_BOOTRESOURCES_WORKFLOW_NAME,
    SYNC_REMOTE_BOOTRESOURCES_WORKFLOW_NAME,
    SYNC_SELECTION_WORKFLOW_NAME,
    SyncRequestParam,
    SyncSelectionParam,
)
from maasservicelayer.builders.notifications import NotificationBuilder
from maasservicelayer.db import Database
from maasservicelayer.db.filters import QuerySpec
from maasservicelayer.db.repositories.bootresources import (
    BootResourceClauseFactory,
)
from maasservicelayer.db.repositories.notifications import (
    NotificationsClauseFactory,
)
from maasservicelayer.models.bootresourcefiles import BootResourceFile
from maasservicelayer.models.bootresources import BootResource
from maasservicelayer.models.bootresourcesets import BootResourceSet
from maasservicelayer.models.bootsources import BootSource
from maasservicelayer.models.bootsourceselections import BootSourceSelection
from maasservicelayer.models.image_manifests import ImageManifest
from maasservicelayer.services import CacheForServices, ServiceCollectionV3
from maasservicelayer.services.boot_sources import BootSourcesService
from maasservicelayer.services.bootresourcefiles import (
    BootResourceFilesService,
)
from maasservicelayer.services.bootresourcefilesync import (
    BootResourceFileSyncService,
)
from maasservicelayer.services.bootresources import BootResourceService
from maasservicelayer.services.bootresourcesets import BootResourceSetsService
from maasservicelayer.services.bootsourcecache import BootSourceCacheService
from maasservicelayer.services.bootsourceselections import (
    BootSourceSelectionsService,
)
from maasservicelayer.services.image_manifests import ImageManifestsService
from maasservicelayer.services.image_sync import ImageSyncService
from maasservicelayer.services.notifications import NotificationsService
from maasservicelayer.services.temporal import TemporalService
from maasservicelayer.simplestreams.models import (
    BootloaderProduct,
    SimpleStreamsProductListType,
)
from maasservicelayer.utils.image_local_files import (
    AsyncLocalBootResourceFile,
    LocalStoreAllocationFail,
    LocalStoreFileSizeMismatch,
    LocalStoreInvalidHash,
)
from maastemporalworker.worker import (
    custom_sandbox_runner,
    pydantic_data_converter,
)
from maastemporalworker.workflow.api_client import MAASAPIClient
from maastemporalworker.workflow.bootresource import (
    BootResourcesActivity,
    CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME,
    DELETE_BOOTRESOURCEFILE_ACTIVITY_NAME,
    DeleteBootResourceWorkflow,
    DISCARD_ERROR_NOTIFICATION_ACTIVITY_NAME,
    DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,
    DownloadBootResourceWorkflow,
    FETCH_MANIFEST_AND_UPDATE_CACHE_ACTIVITY_NAME,
    FetchManifestWorkflow,
    GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,
    GET_FILES_TO_DOWNLOAD_FOR_SELECTION_ACTIVITY_NAME,
    GET_HIGHEST_PRIORITY_SELECTIONS_ACTIVITY_NAME,
    GET_LOCAL_BOOT_RESOURCES_PARAMS_ACTIVITY_NAME,
    GET_SYNCED_REGIONS_ACTIVITY_NAME,
    MasterImageSyncWorkflow,
    REGION_TASK_QUEUE,
    REGISTER_ERROR_NOTIFICATION_ACTIVITY_NAME,
    SyncAllLocalBootResourcesWorkflow,
    SyncBootResourcesWorkflow,
    SyncRemoteBootResourcesWorkflow,
    SyncSelectionWorkflow,
)
from tests.fixtures import AsyncContextManagerMock, AsyncIteratorMock
from tests.maastemporalworker.workflow import (
    TemporalCalls,
    WorkerTestInterceptor,
)

FILE_SIZE = 50


@pytest.fixture
def controller(factory, mocker):
    mocker.patch("maasserver.utils.orm.post_commit_hooks")
    mocker.patch("maasserver.utils.orm.post_commit_do")
    controller = factory.make_RegionRackController()
    yield controller


@pytest.fixture
def maas_data_dir(mocker, tmpdir):
    mocker.patch.dict(os.environ, {"MAAS_DATA": str(tmpdir)})
    yield tmpdir


@pytest.fixture
def image_store_dir(maas_data_dir, mocker):
    store = Path(maas_data_dir) / "image-storage"
    store.mkdir()
    mock_disk_usage = mocker.patch("shutil.disk_usage")
    mock_disk_usage.return_value = (0, 0, 101)  # only care about 'free'
    yield store
    shutil.rmtree(store)


@pytest.fixture
def mock_apiclient():
    m = Mock(MAASAPIClient)
    m.url = "http://test:5240"
    m._mocked_client = Mock(httpx.AsyncClient)
    m.make_client = Mock(return_value=m._mocked_client)
    yield m


@pytest.fixture
def mock_temporal_client():
    yield Mock(Client)


@pytest.fixture
def boot_activities(
    mocker,
    controller,
    mock_apiclient: Mock,
    mock_temporal_client: Mock,
    services_mock: ServiceCollectionV3,
):
    act = BootResourcesActivity(
        Mock(Database), CacheForServices(), mock_temporal_client
    )
    act.apiclient = mock_apiclient
    act.region_id = controller.system_id
    act.report_progress = AsyncMock(return_value=None)
    mocker.patch.object(
        act, "start_transaction"
    ).return_value = AsyncContextManagerMock(services_mock)
    yield act


@pytest.fixture
def a_file(image_store_dir):
    content = b"\x01" * FILE_SIZE
    sha256 = hashlib.sha256()
    sha256.update(content)
    file = image_store_dir / f"{str(sha256.hexdigest())}"
    with file.open("wb") as f:
        f.write(content)
    yield file


@pytest.fixture
def mock_local_file(mocker):
    m = Mock(AsyncLocalBootResourceFile)
    mocker.patch(
        "maastemporalworker.workflow.bootresource.AsyncLocalBootResourceFile"
    ).return_value = m
    m.total_size = FILE_SIZE
    yield m


@pytest.fixture
def activity_env():
    env = ActivityEnvironment()
    env.payload_converter = pydantic_data_converter
    yield env


class TestGetSyncedRegionsForFilesActivity:
    async def test_calls_file_sync_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
    ) -> None:
        services_mock.boot_resource_file_sync = Mock(
            BootResourceFileSyncService
        )
        env = ActivityEnvironment()
        env.payload_converter = pydantic_data_converter
        await env.run(boot_activities.get_synced_regions_for_file, 1)
        services_mock.boot_resource_file_sync.get_synced_regions_for_file.assert_awaited_once_with(
            1
        )


class TestGetBootresourcefileEndpointsActivity:
    async def test_calls_apiclient(
        self, boot_activities: BootResourcesActivity, mock_apiclient: Mock
    ) -> None:
        mock_apiclient.request_async = AsyncMock(
            return_value=[
                {
                    "system_id": "abcdef",
                    "ip_addresses": ["10.0.0.1"],
                },
                {
                    "system_id": "ghijkl",
                    "ip_addresses": ["10.0.0.2"],
                },
                {
                    "system_id": "mnopqr",
                    "ip_addresses": ["10.0.0.3"],
                },
            ]
        )
        env = ActivityEnvironment()
        env.payload_converter = pydantic_data_converter
        endpoints = await env.run(
            boot_activities.get_bootresourcefile_endpoints
        )
        assert endpoints == {
            "abcdef": ["http://10.0.0.1:5240/MAAS/boot-resources/"],
            "ghijkl": ["http://10.0.0.2:5240/MAAS/boot-resources/"],
            "mnopqr": ["http://10.0.0.3:5240/MAAS/boot-resources/"],
        }
        mock_apiclient.request_async.assert_awaited_once_with(
            "GET", f"{mock_apiclient.url}/api/2.0/regioncontrollers/"
        )

    async def test_bug_2058037(
        self, boot_activities: BootResourcesActivity, mock_apiclient: Mock
    ) -> None:
        mock_apiclient.request_async = AsyncMock(
            return_value=[
                {
                    "system_id": "abcdef",
                    "ip_addresses": [],
                },
                {
                    "system_id": "ghijkl",
                    "ip_addresses": ["10.0.0.2"],
                },
                {
                    "system_id": "mnopqr",
                    "ip_addresses": ["10.0.0.3"],
                },
            ]
        )
        env = ActivityEnvironment()
        env.payload_converter = pydantic_data_converter
        with pytest.raises(ApplicationError) as err:
            await env.run(boot_activities.get_bootresourcefile_endpoints)

        assert (
            str(err.value)
            == "Could not retrieve the IP addresses of the region controller 'abcdef' from the API. This activity will be retried until we have the IP for all the region controllers."
        )


class TestDownloadBootresourcefileActivity:
    async def test_valid_file_dont_get_downloaded_again(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        mock_local_file.valid.return_value = True

        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        res = await activity_env.run(
            boot_activities.download_bootresourcefile, param
        )
        assert res is True

        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, mock_local_file.total_size
        )
        mock_apiclient.make_client.assert_not_called()
        mock_local_file.store.assert_not_called()

    async def test_extract_file_emits_heartbeat(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        mock_local_file.valid.return_value = True
        mock_local_file.extract_file.return_value = None

        heartbeats = []
        activity_env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
            extract_paths=["path1", "path2"],
        )
        res = await activity_env.run(
            boot_activities.download_bootresourcefile, param
        )
        assert res is True

        assert heartbeats == [
            "Extracted file in path1",
            "Extracted file in path2",
        ]

        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, mock_local_file.total_size
        )
        mock_apiclient.make_client.assert_not_called()

    async def test_download_file_if_not_valid(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        mock_local_file.valid.side_effect = [False, True]
        chunked_data = [b"foo", b"bar", b""]

        mock_http_response = Mock(httpx.Response)
        mock_http_response.aiter_bytes.return_value = AsyncIteratorMock(
            chunked_data
        )
        mock_apiclient._mocked_client.stream.return_value = (
            AsyncContextManagerMock(mock_http_response)
        )
        mock_store = Mock(AsyncBufferedIOBase)
        mock_local_file.store.return_value = AsyncContextManagerMock(
            mock_store
        )

        heartbeats = []
        activity_env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        res = await activity_env.run(
            boot_activities.download_bootresourcefile, param
        )
        assert res is True

        assert heartbeats == [
            "Downloaded chunk",
            "Downloaded chunk",
            "Downloaded chunk",
            "Download finished",
        ]

        mock_store.write.assert_awaited_once_with(bytearray(b"foobar"))
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, mock_local_file.total_size
        )
        mock_apiclient.make_client.assert_called_once_with(None)
        mock_apiclient._mocked_client.stream.assert_called_once_with(
            "GET",
            "http://maas-image-stream.io",
        )

    async def test_download_file_fails_checksum_check(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        mock_local_file.valid.return_value = False
        mock_local_file.store.side_effect = LocalStoreInvalidHash()

        mock_http_response = Mock(httpx.Response)
        mock_apiclient._mocked_client.stream.return_value = (
            AsyncContextManagerMock(mock_http_response)
        )

        heartbeats = []
        activity_env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        with pytest.raises(ApplicationError) as err:
            await activity_env.run(
                boot_activities.download_bootresourcefile, param
            )

        assert str(err.value) == "Invalid SHA256 checksum"

        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, 0
        )
        mock_apiclient._mocked_client.stream.assert_called_once_with(
            "GET",
            "http://maas-image-stream.io",
        )

    async def test_download_file_raise_out_of_disk_exception(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        mock_local_file.valid.return_value = False
        exception = IOError()
        exception.errno = 28
        mock_local_file.store.side_effect = exception
        mock_http_response = Mock(httpx.Response)
        mock_apiclient._mocked_client.stream.return_value = (
            AsyncContextManagerMock(mock_http_response)
        )

        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        with pytest.raises(ApplicationError):
            await activity_env.run(
                boot_activities.download_bootresourcefile, param
            )

        mock_local_file.unlink.assert_awaited_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, 0
        )

    @pytest.mark.parametrize(
        "exception",
        [CancelledError(), asyncio.CancelledError()],
    )
    async def test_local_file_gets_unlinked_when_activity_is_cancelled(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
        exception,
    ) -> None:
        mock_local_file.valid.return_value = False
        # `store` is not the responsible of raising all these exceptions,
        # but we use it to avoid patching the rest of the function
        mock_local_file.store.side_effect = exception
        mock_http_response = Mock(httpx.Response)
        mock_apiclient._mocked_client.stream.return_value = (
            AsyncContextManagerMock(mock_http_response)
        )

        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        with pytest.raises(type(exception)):
            await activity_env.run(
                boot_activities.download_bootresourcefile, param
            )
        mock_local_file.unlink.assert_called_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, 0
        )

    @pytest.mark.parametrize(
        "exception",
        [
            IOError(),
            httpx.HTTPError("Error"),
            LocalStoreInvalidHash(),
            LocalStoreAllocationFail(),
            LocalStoreFileSizeMismatch(),
        ],
    )
    async def test_download_file_raise_other_exception(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
        activity_env: ActivityEnvironment,
        exception,
    ) -> None:
        mock_local_file.valid.return_value = False
        # `store` is not the responsible of raising all these exceptions,
        # but we use it to avoid patching the rest of the function
        mock_local_file.store.side_effect = exception
        mock_http_response = Mock(httpx.Response)
        mock_apiclient._mocked_client.stream.return_value = (
            AsyncContextManagerMock(mock_http_response)
        )

        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        with pytest.raises(ApplicationError):
            await activity_env.run(
                boot_activities.download_bootresourcefile, param
            )


class TestDeleteBootresourcefileActivity:
    async def test_delete_emits_heartbeat(
        self,
        mocker,
        boot_activities: BootResourcesActivity,
        activity_env: ActivityEnvironment,
    ) -> None:
        mocker.patch("asyncio.sleep")

        heartbeats = []
        activity_env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDeleteParam(
            files=[ResourceIdentifier("0" * 64, "0" * 7)]
        )
        res = await activity_env.run(
            boot_activities.delete_bootresourcefile, param
        )
        assert res is True

        assert heartbeats == ["File deleted"]

    async def test_delete(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        activity_env: ActivityEnvironment,
    ) -> None:
        param = ResourceDeleteParam(
            files=[ResourceIdentifier("0" * 64, "0" * 7)]
        )
        res = await activity_env.run(
            boot_activities.delete_bootresourcefile, param
        )
        assert res is True
        mock_local_file.unlink.assert_called_once()


class TestFetchManifestAndUpdateCacheActivity:
    async def test_calls_service_layer(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
        activity_env: ActivityEnvironment,
    ) -> None:
        mock_boot_source = Mock(BootSource)
        mock_ss_products_list = Mock(SimpleStreamsProductListType)
        mock_ss_products_list.products = [Mock(BootloaderProduct)]
        services_mock.image_sync = Mock(ImageSyncService)
        services_mock.image_sync.check_commissioning_series_selected.return_value = True
        services_mock.image_sync.filter_products_for_selection.return_value = [
            mock_ss_products_list
        ]
        services_mock.boot_sources = Mock(BootSourcesService)
        services_mock.boot_sources.get_many.return_value = [mock_boot_source]
        services_mock.image_manifests = Mock(ImageManifestsService)
        services_mock.boot_source_cache = Mock(BootSourceCacheService)

        heartbeats = []
        activity_env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        await activity_env.run(boot_activities.fetch_manifest_and_update_cache)

        assert heartbeats == ["Downloaded images descriptions"]
        services_mock.image_sync.ensure_boot_source_definition.assert_awaited_once()
        services_mock.boot_sources.get_many.assert_awaited_once()
        services_mock.image_manifests.fetch_and_update.assert_awaited_once()
        services_mock.boot_source_cache.update_from_image_manifest.assert_awaited_once()
        services_mock.image_sync.sync_boot_source_selections_from_msm.assert_awaited_once()
        services_mock.image_sync.check_commissioning_series_selected.assert_awaited_once()


@pytest.mark.parametrize("http_proxy", ["http://proxy.com", None])
class TestGetFilesToDownloadForSelectionActivity:
    async def test_calls_service_layer(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
        activity_env: ActivityEnvironment,
        resource_download_param: ResourceDownloadParam,
        http_proxy: str | None,
    ) -> None:
        boot_source = BootSource(
            id=1,
            url="http://foo.com",
            keyring_filename="/tmp/foo",
            keyring_data=None,
            priority=1,
            skip_keyring_verification=True,
        )
        boot_source_selection = BootSourceSelection(
            id=1,
            os="ubuntu",
            arch="amd64",
            release="noble",
            boot_source_id=boot_source.id,
        )

        mock_product = Mock(BootloaderProduct)
        mock_ss_products_list = Mock(SimpleStreamsProductListType)
        mock_ss_products_list.products = [mock_product]

        image_manifest = Mock(ImageManifest)
        image_manifest.manifest = [mock_ss_products_list]

        services_mock.boot_source_selections = Mock(
            BootSourceSelectionsService
        )
        services_mock.boot_source_selections.get_by_id.return_value = (
            boot_source_selection
        )
        services_mock.boot_sources = Mock(BootSourcesService)
        services_mock.boot_sources.get_by_id.return_value = boot_source
        services_mock.image_manifests = Mock(ImageManifestsService)
        services_mock.image_manifests.get_or_fetch.return_value = (
            image_manifest,
            False,
        )
        services_mock.image_manifests._get_http_proxy.return_value = http_proxy
        services_mock.image_sync = Mock(ImageSyncService)
        services_mock.image_sync.filter_products_for_selection.return_value = [
            mock_ss_products_list
        ]
        services_mock.image_sync.get_files_to_download_from_product_list.return_value = [
            resource_download_param
        ]

        result = await activity_env.run(
            boot_activities.get_files_to_download_for_selection,
            GetFilesToDownloadForSelectionParam(
                selection_id=1,
            ),
        )

        resources_to_download = result.resources
        assert len(resources_to_download) == 1
        assert resources_to_download[0].http_proxy == http_proxy

        services_mock.boot_source_selections.get_by_id.assert_awaited_once_with(
            1
        )
        services_mock.boot_sources.get_by_id.assert_awaited_once_with(1)
        services_mock.image_manifests.get_or_fetch.assert_awaited_once_with(
            boot_source
        )
        services_mock.image_sync.filter_products_for_selection.assert_called_once()
        services_mock.image_sync.get_files_to_download_from_product_list.assert_awaited_once()
        services_mock.image_manifests._get_http_proxy.assert_awaited_once()


class TestGetManuallyUploadedResourcesActivity:
    async def test_calls_service_layer(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
        activity_env: ActivityEnvironment,
    ) -> None:
        boot_resource = BootResource(
            id=1,
            rtype=BootResourceType.UPLOADED,
            name="test",
            architecture="amd64/generic",
            extra={},
            rolling=False,
            base_image="",
        )
        boot_resource_set = BootResourceSet(
            id=1,
            version="20251028",
            label="uploaded",
            resource_id=boot_resource.id,
        )
        boot_resource_files = [
            BootResourceFile(
                id=i,
                filename=f"test-{i}",
                filetype=BootResourceFileType.SQUASHFS_IMAGE,
                sha256=str(i) * 64,
                size=100,
                extra={},
                filename_on_disk=str(i) * 7,
            )
            for i in range(3)
        ]
        services_mock.boot_resources = Mock(BootResourceService)
        services_mock.boot_resources.get_many = AsyncMock(
            return_value=[boot_resource]
        )

        services_mock.boot_resource_sets = Mock(BootResourceSetsService)
        services_mock.boot_resource_sets.get_latest_for_boot_resource = (
            AsyncMock(return_value=boot_resource_set)
        )
        services_mock.boot_resource_files = Mock(BootResourceFilesService)
        services_mock.boot_resource_files.get_files_in_resource_set = (
            AsyncMock(return_value=boot_resource_files)
        )

        resources_result = await activity_env.run(
            boot_activities.get_manually_uploaded_resources
        )

        assert resources_result.resources == [
            ResourceDownloadParam(
                rfile_ids=[file.id],
                source_list=[],  # this will get overridden with the region url
                sha256=file.sha256,
                filename_on_disk=file.filename_on_disk,
                total_size=file.size,
            )
            for file in boot_resource_files
        ]

        services_mock.boot_resources.get_many.assert_awaited_once_with(
            query=QuerySpec(
                where=BootResourceClauseFactory.with_rtype(
                    BootResourceType.UPLOADED
                )
            )
        )

        services_mock.boot_resource_sets.get_latest_for_boot_resource.assert_awaited_once_with(
            boot_resource.id
        )
        services_mock.boot_resource_files.get_files_in_resource_set.assert_awaited_once_with(
            boot_resource_set.id
        )


class TestCleanupOldBootResourcesActivity:
    async def test_calls_image_sync_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
        activity_env: ActivityEnvironment,
    ) -> None:
        services_mock.image_sync = Mock(ImageSyncService)
        services_mock.temporal = Mock(TemporalService)

        await activity_env.run(
            boot_activities.cleanup_old_boot_resource_sets_for_selection,
            CleanupOldBootResourceSetsParam(selection_id=1),
        )
        services_mock.image_sync.delete_old_boot_resource_sets_for_selection.assert_awaited_once()
        services_mock.temporal.post_commit.assert_awaited_once()


class TestGetAllHighestPrioritySelectionsActivity:
    async def test_calls_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
        activity_env: ActivityEnvironment,
    ) -> None:
        services_mock.boot_source_selections = Mock(
            BootSourceSelectionsService
        )

        await activity_env.run(
            boot_activities.get_all_highest_priority_selections,
        )

        services_mock.boot_source_selections.get_all_highest_priority.assert_awaited_once()


class TestRegisterNotificationErrorActivity:
    async def test_calls_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        services_mock.notifications = Mock(NotificationsService)

        await activity_env.run(
            boot_activities.register_error_notification, "error message"
        )

        services_mock.notifications.get_or_create.assert_awaited_once_with(
            query=QuerySpec(
                where=NotificationsClauseFactory.with_ident(
                    NotificationComponent.REGION_IMAGE_SYNC
                )
            ),
            builder=NotificationBuilder(
                ident=NotificationComponent.REGION_IMAGE_SYNC,
                users=True,
                admins=True,
                message="Failed to synchronize boot resources: error message",
                context={},
                user_id=None,
                category=NotificationCategoryEnum.ERROR,
                dismissable=False,
            ),
        )


class TestDiscardNotificationErrorActivity:
    async def test_calls_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: Mock,
        activity_env: ActivityEnvironment,
    ) -> None:
        services_mock.notifications = Mock(NotificationsService)

        await activity_env.run(boot_activities.discard_error_notification)

        services_mock.notifications.delete_one.assert_awaited_once_with(
            query=QuerySpec(
                where=NotificationsClauseFactory.with_ident(
                    NotificationComponent.REGION_IMAGE_SYNC
                )
            ),
        )


@pytest.fixture
async def env() -> AsyncGenerator[WorkflowEnvironment, None]:
    env = await WorkflowEnvironment.start_time_skipping()
    yield env
    await env.shutdown()


@pytest.fixture
async def client(env: WorkflowEnvironment) -> Client:
    config = env.client.config()
    config["data_converter"] = pydantic_data_converter
    client = Client(**config)
    return client


class MockActivities:
    def __init__(self):
        # Return values for activities. You can override them in the single test.
        # The naming convention is <activity_name>_result
        self.get_bootresourcefile_endpoints_result = {}
        self.download_bootresourcefile_result = True
        self.get_synced_regions_for_file_result = []
        self.get_all_highest_priority_selections_result = [1, 2]
        self.get_manually_uploaded_resources_result = (
            GetLocalBootResourcesParamReturnValue(resources=[])
        )
        self.get_files_to_download_for_selection_result = {
            1: (
                GetFilesToDownloadReturnValue(
                    resources=[
                        ResourceDownloadParam(
                            rfile_ids=[1],
                            source_list=["http://maas-image-stream.io"],
                            sha256="1" * 64,
                            filename_on_disk="1" * 7,
                            total_size=100,
                        )
                    ]
                )
            ),
            2: (
                GetFilesToDownloadReturnValue(
                    resources=[
                        ResourceDownloadParam(
                            rfile_ids=[2],
                            source_list=["http://maas-image-stream.io"],
                            sha256="2" * 64,
                            filename_on_disk="2" * 7,
                            total_size=100,
                        )
                    ]
                )
            ),
        }
        self.delete_bootresourcefile_result = True

    @activity.defn(name=GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME)
    async def get_bootresourcefile_endpoints(self) -> dict[str, list]:
        return self.get_bootresourcefile_endpoints_result

    @activity.defn(name=DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME)
    async def download_bootresourcefile(
        self, param: ResourceDownloadParam
    ) -> bool:
        return self.download_bootresourcefile_result

    @activity.defn(name=GET_SYNCED_REGIONS_ACTIVITY_NAME)
    async def get_synced_regions_for_file(self, file_id: int) -> list[str]:
        return self.get_synced_regions_for_file_result

    @activity.defn(name=FETCH_MANIFEST_AND_UPDATE_CACHE_ACTIVITY_NAME)
    async def fetch_manifest_and_update_cache(
        self,
    ) -> None:
        return None

    @activity.defn(name=GET_HIGHEST_PRIORITY_SELECTIONS_ACTIVITY_NAME)
    async def get_all_highest_priority_selections(self) -> list[int]:
        return self.get_all_highest_priority_selections_result

    @activity.defn(name=GET_FILES_TO_DOWNLOAD_FOR_SELECTION_ACTIVITY_NAME)
    async def get_files_to_download_for_selection(
        self, param: GetFilesToDownloadForSelectionParam
    ) -> GetFilesToDownloadReturnValue:
        return self.get_files_to_download_for_selection_result[
            param.selection_id
        ]

    @activity.defn(name=GET_LOCAL_BOOT_RESOURCES_PARAMS_ACTIVITY_NAME)
    async def get_manually_uploaded_resources(
        self,
    ) -> GetLocalBootResourcesParamReturnValue:
        return self.get_manually_uploaded_resources_result

    @activity.defn(name=CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME)
    async def cleanup_old_boot_resource_sets_for_selection(
        self,
        param: CleanupOldBootResourceSetsParam,
    ) -> None:
        pass

    @activity.defn(name=REGISTER_ERROR_NOTIFICATION_ACTIVITY_NAME)
    async def register_error_notification(self, err_msg: str) -> None:
        pass

    @activity.defn(name=DISCARD_ERROR_NOTIFICATION_ACTIVITY_NAME)
    async def discard_error_notification(self) -> None:
        pass

    @activity.defn(name=DELETE_BOOTRESOURCEFILE_ACTIVITY_NAME)
    async def delete_bootresourcefile(
        self, param: ResourceDeleteParam
    ) -> bool:
        return self.delete_bootresourcefile_result


@pytest.fixture
def region1_system_id() -> str:
    return "abcdef"


@pytest.fixture
def region2_system_id() -> str:
    return "ghijkl"


@pytest.fixture
def region3_system_id() -> str:
    return "mnopqr"


@pytest.fixture
def endpoints_single_region(region1_system_id: str):
    return {region1_system_id: ["http://10.0.0.1:5240/MAAS/boot-resources/"]}


@pytest.fixture
def endpoints_three_regions(
    region1_system_id: str, region2_system_id: str, region3_system_id: str
):
    """Three region endpoint configuration"""
    return {
        region1_system_id: ["http://10.0.0.1:5240/MAAS/boot-resources/"],
        region2_system_id: ["http://10.0.0.2:5240/MAAS/boot-resources/"],
        region3_system_id: ["http://10.0.0.3:5240/MAAS/boot-resources/"],
    }


@pytest.fixture
def resource_download_param():
    return ResourceDownloadParam(
        rfile_ids=[1],
        source_list=["http://maas-image-stream.io"],
        sha256="0" * 64,
        filename_on_disk="0" * 7,
        total_size=100,
    )


@pytest.fixture
def sync_request(resource_download_param: ResourceDownloadParam):
    return SyncRequestParam(resource=resource_download_param)


@pytest.fixture
def mock_activities():
    return MockActivities()


@pytest.fixture
async def _shared_queue_worker(
    client: Client,
    mock_activities: MockActivities,
    worker_test_interceptor: WorkerTestInterceptor,
):
    """Temporal worker that listens on the shared task queue."""
    async with Worker(
        client=client,
        task_queue=REGION_TASK_QUEUE,
        workflows=[
            DeleteBootResourceWorkflow,
            DownloadBootResourceWorkflow,
            SyncRemoteBootResourcesWorkflow,
            SyncBootResourcesWorkflow,
            SyncSelectionWorkflow,
            SyncAllLocalBootResourcesWorkflow,
            MasterImageSyncWorkflow,
            FetchManifestWorkflow,
        ],
        activities=[
            mock_activities.fetch_manifest_and_update_cache,
            mock_activities.download_bootresourcefile,
            mock_activities.get_bootresourcefile_endpoints,
            mock_activities.get_files_to_download_for_selection,
            mock_activities.get_synced_regions_for_file,
            mock_activities.get_all_highest_priority_selections,
            mock_activities.cleanup_old_boot_resource_sets_for_selection,
            mock_activities.register_error_notification,
            mock_activities.discard_error_notification,
        ],
        workflow_runner=custom_sandbox_runner(),
        interceptors=[worker_test_interceptor],
    ):
        yield


def _make_region_worker(
    client: Client,
    system_id: str,
    mock_activities: MockActivities,
    worker_test_interceptor: WorkerTestInterceptor,
) -> Worker:
    return Worker(
        client=client,
        task_queue=f"region:{system_id}",
        workflows=[
            DownloadBootResourceWorkflow,
        ],
        activities=[
            mock_activities.delete_bootresourcefile,
            mock_activities.download_bootresourcefile,
        ],
        workflow_runner=custom_sandbox_runner(),
        interceptors=[worker_test_interceptor],
    )


@pytest.fixture
async def single_region_workers(
    client: Client,
    region1_system_id: str,
    endpoints_single_region: dict[str, list],
    mock_activities: MockActivities,
    worker_test_interceptor: WorkerTestInterceptor,
    _shared_queue_worker,
):
    """Setup the temporal workers for a single region scenario."""
    mock_activities.get_bootresourcefile_endpoints_result = (
        endpoints_single_region
    )
    async with _make_region_worker(
        client, region1_system_id, mock_activities, worker_test_interceptor
    ):
        yield


@pytest.fixture
async def three_regions_workers(
    client: Client,
    region1_system_id: str,
    region2_system_id: str,
    region3_system_id: str,
    endpoints_three_regions: dict[str, list],
    mock_activities: MockActivities,
    worker_test_interceptor: WorkerTestInterceptor,
    _shared_queue_worker,
):
    """Setup the temporal workers for an HA scenario."""
    mock_activities.get_bootresourcefile_endpoints_result = (
        endpoints_three_regions
    )
    async with (
        _make_region_worker(
            client, region1_system_id, mock_activities, worker_test_interceptor
        ),
        _make_region_worker(
            client, region2_system_id, mock_activities, worker_test_interceptor
        ),
        _make_region_worker(
            client, region3_system_id, mock_activities, worker_test_interceptor
        ),
    ):
        yield


class TestSyncBootResourcesWorkflow:
    @pytest.mark.asyncio
    async def test_single_region_sync(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
        sync_request: SyncRequestParam,
    ):
        await client.execute_workflow(
            SyncBootResourcesWorkflow.run,
            sync_request,
            id="test-sync-single",
            task_queue=REGION_TASK_QUEUE,
        )

        # Only one region, nothing to sync
        temporal_calls.assert_activity_calls(
            [GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME]
        )
        temporal_calls.assert_child_workflow_calls([])

    @pytest.mark.asyncio
    async def test_three_region_sync_with_missing_regions(
        self,
        client: Client,
        three_regions_workers,
        sync_request: SyncRequestParam,
        region1_system_id: str,
        temporal_calls: TemporalCalls,
        mock_activities: MockActivities,
    ):
        # Only one synced region
        mock_activities.get_synced_regions_for_file_result = [
            region1_system_id
        ]
        await client.execute_workflow(
            SyncBootResourcesWorkflow.run,
            sync_request,
            id="test-sync-three",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_calls(
            [
                GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,
                GET_SYNCED_REGIONS_ACTIVITY_NAME,
                DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,
                DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,
            ]
        )
        temporal_calls.assert_child_workflow_called_times(
            DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME, times=2
        )

    @pytest.mark.asyncio
    async def test_failed_sync_to_regions(
        self,
        client: Client,
        three_regions_workers,
        sync_request: SyncRequestParam,
        region1_system_id: str,
        mock_activities: MockActivities,
    ):
        """Test workflow fails when sync to other regions fails"""
        mock_activities.get_synced_regions_for_file_result = [
            region1_system_id
        ]
        # Make the download wf fail
        mock_activities.download_bootresourcefile_result = False

        with (
            pytest.raises(WorkflowFailureError) as exc_info,
        ):
            await client.execute_workflow(
                SyncBootResourcesWorkflow.run,
                sync_request,
                id="test-failed-sync",
                task_queue=REGION_TASK_QUEUE,
            )

            # The exception returned is WorkflowFailureError.
            # The ApplicationError we raise is available in the `cause` attribute.
            assert "could not be synced" in str(exc_info.value.cause.message)
            assert exc_info.value.cause.non_retryable

    @pytest.mark.asyncio
    async def test_no_synced_regions_available(
        self,
        client: Client,
        sync_request: SyncRequestParam,
        three_regions_workers,
        mock_activities: MockActivities,
    ):
        """Test workflow fails when no regions have the complete file"""
        mock_activities.get_synced_regions_for_file_result = []  # No region have the file

        with (
            pytest.raises(WorkflowFailureError) as exc_info,
        ):
            await client.execute_workflow(
                SyncBootResourcesWorkflow.run,
                sync_request,
                id="test-no-synced-regions",
                task_queue=REGION_TASK_QUEUE,
            )

            # The exception returned is WorkflowFailureError.
            # The ApplicationError we raise is available in the `cause` attribute.
            assert "has no complete copy available" in str(
                exc_info.value.cause.message
            )
            assert not exc_info.value.cause.non_retryable


class TestSyncRemoteBootResourcesWorkflow:
    @pytest.mark.asyncio
    async def test_remote_sync_signals_master(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
        sync_request: SyncRequestParam,
    ):
        await client.execute_workflow(
            SyncRemoteBootResourcesWorkflow.run,
            sync_request,
            id="test-sync-single",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_child_workflow_calls(
            [
                DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
                SYNC_BOOTRESOURCES_WORKFLOW_NAME,
            ]
        )

    @pytest.mark.asyncio
    async def test_failed_upstream_download(
        self,
        client: Client,
        single_region_workers,
        sync_request: SyncRequestParam,
        mock_activities: MockActivities,
    ):
        """Test workflow fails when upstream download fails"""
        mock_activities.download_bootresourcefile_result = False
        with (
            pytest.raises(WorkflowFailureError) as exc_info,
        ):
            await client.execute_workflow(
                SyncRemoteBootResourcesWorkflow.run,
                sync_request,
                id="test-failed-download",
                task_queue=REGION_TASK_QUEUE,
            )

            # The exception returned is WorkflowFailureError.
            # The ApplicationError we raise is available in the `cause` attribute.
            assert "could not be downloaded" in exc_info.value.cause.message
            assert exc_info.value.cause.non_retryable


class TestSyncSelectionWorkflow:
    """Tests for selection-based image sync"""

    async def test_nothing_to_download(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
        mock_activities: MockActivities,
    ):
        mock_activities.get_all_highest_priority_selections_result = [1]
        mock_activities.get_files_to_download_for_selection_result = {
            1: GetFilesToDownloadReturnValue(resources=[])
        }
        await client.execute_workflow(
            SyncSelectionWorkflow.run,
            SyncSelectionParam(selection_id=1),
            id="test-nothing-to-download",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_child_workflow_not_called(
            SYNC_REMOTE_BOOTRESOURCES_WORKFLOW_NAME
        )

    async def test_single_region(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
    ):
        await client.execute_workflow(
            SyncSelectionWorkflow.run,
            SyncSelectionParam(selection_id=1),
            id="test-nothing-to-download",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_calls(
            [
                GET_FILES_TO_DOWNLOAD_FOR_SELECTION_ACTIVITY_NAME,
                DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,  # SyncBootResources wf
                GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,  # SyncBootResources wf
                CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME,
            ]
        )

        temporal_calls.assert_child_workflow_calls(
            [
                SYNC_REMOTE_BOOTRESOURCES_WORKFLOW_NAME,
                DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
                SYNC_BOOTRESOURCES_WORKFLOW_NAME,
            ]
        )

    async def test_three_regions(
        self,
        client: Client,
        three_regions_workers,
        temporal_calls: TemporalCalls,
        region1_system_id: str,
        mock_activities: MockActivities,
    ):
        # One synced region after the download
        mock_activities.get_synced_regions_for_file_result = [
            region1_system_id
        ]
        await client.execute_workflow(
            SyncSelectionWorkflow.run,
            SyncSelectionParam(selection_id=1),
            id="test-nothing-to-download",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_calls(
            [
                GET_FILES_TO_DOWNLOAD_FOR_SELECTION_ACTIVITY_NAME,
                DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,  # SyncRemoteBootResources wf
                GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,  # SyncBootResources wf
                GET_SYNCED_REGIONS_ACTIVITY_NAME,  # SyncBootResources wf
                DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,  # SyncBootResources wf
                DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,  # SyncBootResources wf
                CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME,
            ]
        )

        temporal_calls.assert_child_workflow_calls(
            [
                SYNC_REMOTE_BOOTRESOURCES_WORKFLOW_NAME,
                DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
                SYNC_BOOTRESOURCES_WORKFLOW_NAME,
                DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
                DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
            ]
        )


class TestSyncAllBootResourcesWorkflow:
    async def test_no_local_resources(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
    ) -> None:
        await client.execute_workflow(
            SyncAllLocalBootResourcesWorkflow.run,
            id="test-sync-all-local",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_called_once(
            GET_LOCAL_BOOT_RESOURCES_PARAMS_ACTIVITY_NAME
        )
        temporal_calls.assert_child_workflow_not_called(
            SYNC_BOOTRESOURCES_WORKFLOW_NAME
        )

    async def test_single_region(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
        mock_activities: MockActivities,
        resource_download_param: ResourceDownloadParam,
    ) -> None:
        mock_activities.get_manually_uploaded_resources_result = (
            GetLocalBootResourcesParamReturnValue(
                resources=[resource_download_param]
            )
        )
        await client.execute_workflow(
            SyncAllLocalBootResourcesWorkflow.run,
            id="test-sync-all-local",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_called_once(
            GET_LOCAL_BOOT_RESOURCES_PARAMS_ACTIVITY_NAME
        )
        temporal_calls.assert_child_workflow_called_once(
            SYNC_BOOTRESOURCES_WORKFLOW_NAME
        )
        # Single region, nothing to sync
        temporal_calls.assert_child_workflow_not_called(
            DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME
        )

    async def test_three_region(
        self,
        client: Client,
        three_region_workers,
        temporal_calls: TemporalCalls,
        region1_system_id: str,
        mock_activities: MockActivities,
        resource_download_param: ResourceDownloadParam,
    ) -> None:
        mock_activities.get_manually_uploaded_resources_result = (
            GetLocalBootResourcesParamReturnValue(
                resources=[resource_download_param]
            )
        )
        mock_activities.get_synced_regions_for_file_result = [
            region1_system_id
        ]
        await client.execute_workflow(
            SyncAllLocalBootResourcesWorkflow.run,
            id="test-sync-all-local",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_called_once(
            GET_LOCAL_BOOT_RESOURCES_PARAMS_ACTIVITY_NAME
        )
        temporal_calls.assert_child_workflow_called_once(
            SYNC_BOOTRESOURCES_WORKFLOW_NAME
        )
        # two regions need the file
        temporal_calls.assert_child_workflow_called_times(
            DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME, times=2
        )


class TestMasterImageSyncWorkflow:
    """Tests for MasterImageSyncWorkflow"""

    @pytest.mark.asyncio
    async def test_single_region_master_workflow(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
    ):
        """Test master workflow with single region"""
        await client.execute_workflow(
            MasterImageSyncWorkflow.run,
            id="test-master-single",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_child_workflow_called_times(
            SYNC_SELECTION_WORKFLOW_NAME, times=2
        )
        # One download per selection and per region
        temporal_calls.assert_child_workflow_called_times(
            DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME, times=2
        )
        temporal_calls.assert_activity_called_once(
            DISCARD_ERROR_NOTIFICATION_ACTIVITY_NAME
        )
        temporal_calls.assert_child_workflow_called_once(
            SYNC_ALL_LOCAL_BOOTRESOURCES_WORKFLOW_NAME
        )

    @pytest.mark.asyncio
    async def test_three_region_master_workflow(
        self,
        client: Client,
        three_regions_workers,
        temporal_calls: TemporalCalls,
        region1_system_id: str,
        mock_activities: MockActivities,
    ):
        """Test master workflow schedules sync for all regions"""
        mock_activities.get_synced_regions_for_file_result = [
            region1_system_id
        ]
        await client.execute_workflow(
            MasterImageSyncWorkflow.run,
            id="test-master-three",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_child_workflow_called_times(
            SYNC_SELECTION_WORKFLOW_NAME, times=2
        )
        # One download per selection and per region
        temporal_calls.assert_child_workflow_called_times(
            DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME, times=6
        )
        temporal_calls.assert_activity_called_once(
            DISCARD_ERROR_NOTIFICATION_ACTIVITY_NAME
        )
        temporal_calls.assert_child_workflow_called_once(
            SYNC_ALL_LOCAL_BOOTRESOURCES_WORKFLOW_NAME
        )

    @pytest.mark.asyncio
    async def test_creates_notification_on_error(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
        mock_activities: MockActivities,
    ):
        mock_activities.download_bootresourcefile_result = False
        await client.execute_workflow(
            MasterImageSyncWorkflow.run,
            id="test-error-notification",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_activity_called_once(
            REGISTER_ERROR_NOTIFICATION_ACTIVITY_NAME,
        )

    @pytest.mark.asyncio
    async def test_already_started_workflow_handling(
        self,
        client: Client,
        single_region_workers,
        temporal_calls: TemporalCalls,
        mock_activities: MockActivities,
    ):
        """Test workflow handles already started child workflows gracefully"""
        # Two selections to sync
        mock_activities.get_all_highest_priority_selections_result = [1, 2]

        # SyncSelectionWorflow for selection with id 1 already running
        await client.start_workflow(
            SYNC_SELECTION_WORKFLOW_NAME,
            SyncSelectionParam(selection_id=1),
            id="sync-selection:1",
            task_queue=REGION_TASK_QUEUE,
        )
        # Should not raise error
        await client.execute_workflow(
            MasterImageSyncWorkflow.run,
            id="test-already-started",
            task_queue=REGION_TASK_QUEUE,
        )

        temporal_calls.assert_child_workflow_called_times(
            SYNC_REMOTE_BOOTRESOURCES_WORKFLOW_NAME, times=2
        )
