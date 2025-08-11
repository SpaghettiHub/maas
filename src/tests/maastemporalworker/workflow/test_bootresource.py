#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import asyncio
import hashlib
from itertools import islice, repeat
import os
from pathlib import Path
import shutil
from unittest.mock import AsyncMock, call, Mock, patch

from aiohttp import ClientError, ClientResponse
import pytest
from temporalio import activity
from temporalio.client import (
    Client,
    WorkflowExecution,
    WorkflowFailureError,
    WorkflowHandle,
)
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.testing import ActivityEnvironment, WorkflowEnvironment
from temporalio.worker import Worker

from maascommon.workflows.bootresource import (
    CancelObsoleteDownloadWorkflowsParam,
    CleanupOldBootResourceParam,
    GetFilesToDownloadReturnValue,
    MASTER_IMAGE_SYNC_WORKFLOW_NAME,
    ResourceDeleteParam,
    ResourceDownloadParam,
    ResourceIdentifier,
    SYNC_BOOTRESOURCES_WORKFLOW_NAME,
    SyncRequestParam,
)
from maasservicelayer.db import Database
from maasservicelayer.models.bootsources import BootSource
from maasservicelayer.services import CacheForServices, ServiceCollectionV3
from maasservicelayer.services.bootresourcefilesync import (
    BootResourceFileSyncService,
)
from maasservicelayer.services.image_sync import ImageSyncService
from maasservicelayer.simplestreams.models import (
    BootloaderProduct,
    SimpleStreamsProductList,
)
from maasservicelayer.utils.image_local_files import (
    LocalBootResourceFile,
    LocalStoreInvalidHash,
    LocalStoreWriteBeyondEOF,
    MMapedLocalFile,
)
from maastemporalworker.workflow.api_client import MAASAPIClient
from maastemporalworker.workflow.bootresource import (
    BootResourcesActivity,
    CANCEL_OBSOLETE_DOWNLOAD_WORKFLOWS_ACTIVITY_NAME,
    CHECK_DISK_SPACE_ACTIVITY_NAME,
    CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME,
    DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,
    GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,
    GET_FILES_TO_DOWNLOAD_ACTIVITY_NAME,
    GET_SYNCED_REGIONS_ACTIVITY_NAME,
    MasterImageSyncWorkflow,
    SET_GLOBAL_DEFAULT_RELEASES_ACTIVITY_NAME,
    SpaceRequirementParam,
    SyncBootResourcesWorkflow,
)
from tests.fixtures import AsyncContextManagerMock, AsyncIteratorMock

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
    content = bytes(b"".join(islice(repeat(b"\x01"), FILE_SIZE)))
    sha256 = hashlib.sha256()
    sha256.update(content)
    file = image_store_dir / f"{str(sha256.hexdigest())}"
    with file.open("wb") as f:
        f.write(content)
    yield file


@pytest.fixture
def mock_local_file(mocker):
    m = Mock(LocalBootResourceFile)
    mocker.patch(
        "maastemporalworker.workflow.bootresource.LocalBootResourceFile"
    ).return_value = m
    yield m


@pytest.mark.usefixtures("maasdb")
class TestCheckDiskSpace:
    async def test_check_disk_space_total(
        self, boot_activities, image_store_dir
    ):
        env = ActivityEnvironment()
        param = SpaceRequirementParam(total_resources_size=100)
        ok = await env.run(boot_activities.check_disk_space, param)
        assert ok

    async def test_check_disk_space_total_has_space(
        self, boot_activities, image_store_dir, a_file
    ):
        env = ActivityEnvironment()
        param = SpaceRequirementParam(total_resources_size=70)
        ok = await env.run(boot_activities.check_disk_space, param)
        assert ok

    async def test_check_disk_space_total_full(
        self, boot_activities, image_store_dir
    ):
        env = ActivityEnvironment()
        param = SpaceRequirementParam(total_resources_size=120)
        ok = await env.run(boot_activities.check_disk_space, param)
        assert not ok

    async def test_check_disk_space_min_free_space(
        self, boot_activities, image_store_dir
    ):
        env = ActivityEnvironment()
        param = SpaceRequirementParam(min_free_space=50)
        ok = await env.run(boot_activities.check_disk_space, param)
        assert ok

    async def test_check_disk_space_min_free_space_full(
        self, boot_activities, image_store_dir
    ):
        env = ActivityEnvironment()
        param = SpaceRequirementParam(min_free_space=500)
        ok = await env.run(boot_activities.check_disk_space, param)
        assert not ok


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
        async with env.run(boot_activities.start_transaction) as services:
            assert services == services_mock
        await env.run(boot_activities.get_synced_regions_for_files, {1, 2, 3})
        services_mock.boot_resource_file_sync.get_synced_regions.assert_awaited_once_with(
            {1, 2, 3}
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
        with pytest.raises(ApplicationError) as err:
            await env.run(boot_activities.get_bootresourcefile_endpoints)

        assert (
            str(err.value)
            == "Could not retrieve the IP addresses of the region controller 'abcdef' from the API. This activity will be retried until we have the IP for all the region controllers."
        )


class TestDownloadBootresourcefileActivity:
    async def test_failed_acquiring_lock_emits_heartbeat(
        self,
        mocker,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
    ) -> None:
        mock_local_file.acquire_lock.side_effect = [False, True]
        mock_local_file.avalid.return_value = True
        mocker.patch("asyncio.sleep")

        heartbeats = []
        env = ActivityEnvironment()
        env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        res = await env.run(boot_activities.download_bootresourcefile, param)
        assert res is True

        assert heartbeats == ["Waiting for file lock"]
        mock_local_file.release_lock.assert_called_once()

    async def test_valid_file_dont_get_downloaded_again(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
    ) -> None:
        mock_local_file.acquire_lock.return_value = True
        mock_local_file.avalid.return_value = True

        env = ActivityEnvironment()
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        res = await env.run(boot_activities.download_bootresourcefile, param)
        assert res is True

        mock_local_file.commit.assert_called_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, mock_local_file.size
        )
        mock_apiclient.session.get.assert_not_called()
        mock_local_file.release_lock.assert_called_once()

    async def test_extract_file_emits_heartbeat(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
    ) -> None:
        mock_local_file.acquire_lock.return_value = True
        mock_local_file.avalid.return_value = True
        mock_local_file.extract_file.return_value = None

        heartbeats = []
        env = ActivityEnvironment()
        env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
            extract_paths=["path1", "path2"],
        )
        res = await env.run(boot_activities.download_bootresourcefile, param)
        assert res is True

        assert heartbeats == [
            "Extracted file in path1",
            "Extracted file in path2",
        ]

        mock_local_file.commit.assert_called_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, mock_local_file.size
        )
        mock_apiclient.session.get.assert_not_called()
        mock_local_file.release_lock.assert_called_once()

    async def test_download_file_if_not_valid(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
    ) -> None:
        mock_local_file.acquire_lock.return_value = True
        mock_local_file.avalid.side_effect = [False, True]
        chunked_data = [
            (b"foo", True),
            (b"bar", True),
            (b"", False),
        ]

        mock_http_response = Mock(ClientResponse)
        mock_http_response.content.iter_chunks.return_value = (
            AsyncIteratorMock(chunked_data)
        )
        mock_apiclient.session.get.return_value = AsyncContextManagerMock(
            mock_http_response
        )
        mock_store = Mock(MMapedLocalFile)
        mock_local_file.astore.return_value = AsyncContextManagerMock(
            mock_store
        )

        heartbeats = []
        env = ActivityEnvironment()
        env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        res = await env.run(boot_activities.download_bootresourcefile, param)
        assert res is True

        assert heartbeats == [
            "Downloaded chunk",
            "Downloaded chunk",
            "Downloaded chunk",
            "Finished download, doing checksum",
        ]

        mock_store.write.assert_has_calls(
            [
                call(b"foo"),
                call(b"bar"),
                call(b""),
            ]
        )
        mock_local_file.commit.assert_called_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, mock_local_file.size
        )
        mock_apiclient.session.get.assert_called_once_with(
            "http://maas-image-stream.io",
            verify_ssl=False,
            chunked=True,
            proxy=None,
        )
        mock_local_file.release_lock.assert_called_once()

    async def test_download_file_fails_checksum_check(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        mock_apiclient: Mock,
    ) -> None:
        mock_local_file.acquire_lock.return_value = True
        mock_local_file.avalid.side_effect = [False, False]
        chunked_data = [
            (b"foo", True),
            (b"bar", True),
            (b"", False),
        ]

        mock_http_response = Mock(ClientResponse)
        mock_http_response.content.iter_chunks.return_value = (
            AsyncIteratorMock(chunked_data)
        )
        mock_apiclient.session.get.return_value = AsyncContextManagerMock(
            mock_http_response
        )
        mock_local_file.astore.return_value = AsyncContextManagerMock(
            Mock(MMapedLocalFile)
        )

        heartbeats = []
        env = ActivityEnvironment()
        env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        with pytest.raises(ApplicationError) as err:
            await env.run(boot_activities.download_bootresourcefile, param)

        assert str(err.value) == "Invalid checksum"

        assert heartbeats == [
            "Downloaded chunk",
            "Downloaded chunk",
            "Downloaded chunk",
            "Finished download, doing checksum",
        ]

        mock_local_file.unlink.assert_called_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, 0
        )
        mock_apiclient.session.get.assert_called_once_with(
            "http://maas-image-stream.io",
            verify_ssl=False,
            chunked=True,
            proxy=None,
        )
        mock_local_file.release_lock.assert_called_once()

    async def test_download_file_raise_out_of_disk_exception(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
    ) -> None:
        # Acquire lock is not the responsible of raising all these exceptions,
        # but we use it to avoid patching the rest of the function
        exception = IOError()
        exception.errno = 28
        mock_local_file.acquire_lock.side_effect = exception
        env = ActivityEnvironment()
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        res = await env.run(boot_activities.download_bootresourcefile, param)
        assert res is False
        mock_local_file.unlink.assert_called_once()
        boot_activities.report_progress.assert_awaited_once_with(
            param.rfile_ids, 0
        )
        mock_local_file.release_lock.assert_called_once()

    @pytest.mark.parametrize(
        "exception",
        [
            IOError(),
            ClientError(),
            LocalStoreInvalidHash(),
            LocalStoreWriteBeyondEOF(),
        ],
    )
    async def test_download_file_raise_other_exception(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
        exception,
    ) -> None:
        # Acquire lock is not the responsible of raising all these exceptions,
        # but we use it to avoid patching the rest of the function
        mock_local_file.acquire_lock.side_effect = exception
        env = ActivityEnvironment()
        param = ResourceDownloadParam(
            rfile_ids=[1],
            source_list=["http://maas-image-stream.io"],
            sha256="0" * 64,
            filename_on_disk="0" * 7,
            total_size=100,
        )
        with pytest.raises(ApplicationError):
            await env.run(boot_activities.download_bootresourcefile, param)
        mock_local_file.release_lock.assert_called_once()


class TestDeleteBootresourcefileActivity:
    async def test_delete_emits_heartbeat(
        self,
        mocker,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
    ) -> None:
        mock_local_file.acquire_lock.side_effect = [False, True]
        mocker.patch("asyncio.sleep")

        heartbeats = []
        env = ActivityEnvironment()
        env.on_heartbeat = lambda *args: heartbeats.append(args[0])
        param = ResourceDeleteParam(
            files=[ResourceIdentifier("0" * 64, "0" * 7)]
        )
        res = await env.run(boot_activities.delete_bootresourcefile, param)
        assert res is True

        assert heartbeats == ["Waiting for file lock"]

    async def test_delete(
        self,
        mock_local_file: Mock,
        boot_activities: BootResourcesActivity,
    ) -> None:
        mock_local_file.acquire_lock.return_value = True

        env = ActivityEnvironment()
        param = ResourceDeleteParam(
            files=[ResourceIdentifier("0" * 64, "0" * 7)]
        )
        res = await env.run(boot_activities.delete_bootresourcefile, param)
        assert res is True
        mock_local_file.acquire_lock.assert_called_once()
        mock_local_file.unlink.assert_called_once()
        mock_local_file.release_lock.assert_called_once()


class TestGetFilesToDownloadActivity:
    async def test_calls_image_sync_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
    ) -> None:
        mock_boot_source = Mock(BootSource)
        mock_boot_source.id = 1
        mock_ss_products_list = Mock(SimpleStreamsProductList)
        mock_ss_products_list.products = [Mock(BootloaderProduct)]
        services_mock.image_sync = Mock(ImageSyncService)
        services_mock.image_sync.fetch_images_metadata.return_value = {
            mock_boot_source: [mock_ss_products_list]
        }
        services_mock.image_sync.check_commissioning_series_selected.return_value = True
        services_mock.image_sync.filter_products.return_value = {
            mock_boot_source: mock_ss_products_list
        }
        services_mock.image_sync.get_files_to_download_from_product_list.return_value = (
            {},
            {1},
        )

        env = ActivityEnvironment()
        await env.run(boot_activities.get_files_to_download)

        services_mock.image_sync.fetch_images_metadata.assert_awaited_once()
        services_mock.image_sync.cache_boot_source_from_simplestreams_products.assert_awaited_once()
        services_mock.image_sync.sync_boot_source_selections_from_msm.assert_awaited_once()
        services_mock.image_sync.check_commissioning_series_selected.assert_awaited_once()
        services_mock.image_sync.filter_products.assert_awaited_once()
        services_mock.image_sync.get_files_to_download_from_product_list.assert_awaited_once()


class TestGetGlobalDefaultReleaseActivity:
    async def test_calls_image_sync_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
    ) -> None:
        services_mock.image_sync = Mock(ImageSyncService)

        env = ActivityEnvironment()
        await env.run(boot_activities.set_global_default_releases)
        services_mock.image_sync.set_global_default_releases.assert_awaited_once()


class TestCleanupOldBootResourcesActivity:
    async def test_calls_image_sync_service(
        self,
        boot_activities: BootResourcesActivity,
        services_mock: ServiceCollectionV3,
    ) -> None:
        services_mock.image_sync = Mock(ImageSyncService)

        env = ActivityEnvironment()
        param = CleanupOldBootResourceParam(
            boot_resource_ids_to_keep={1, 2, 3}
        )
        await env.run(boot_activities.cleanup_old_boot_resources, param)
        services_mock.image_sync.delete_old_boot_resources.assert_awaited_once_with(
            {1, 2, 3}
        )
        services_mock.image_sync.delete_old_boot_resource_sets.assert_awaited_once()


class TestCancelObsoleteDownloadWorkflowsActivity:
    async def test_cancel(
        self,
        boot_activities: BootResourcesActivity,
        mock_temporal_client: Mock,
    ) -> None:
        shas = {"a" * 64, "b" * 64, "c" * 64}
        wf1 = Mock(WorkflowExecution)
        wf1.id = f"{SYNC_BOOTRESOURCES_WORKFLOW_NAME}:{'0' * 12}"
        wf2 = Mock(WorkflowExecution)
        wf2.id = f"{SYNC_BOOTRESOURCES_WORKFLOW_NAME}:{'1' * 12}"
        wf3 = Mock(WorkflowExecution)
        wf3.id = f"{SYNC_BOOTRESOURCES_WORKFLOW_NAME}:{'a' * 12}"

        workflows = [wf1, wf2, wf3]
        handle_wf1 = AsyncMock(WorkflowHandle)
        handle_wf2 = AsyncMock(WorkflowHandle)

        mock_temporal_client.list_workflows.return_value = AsyncIteratorMock(
            workflows
        )
        mock_temporal_client.get_workflow_handle.side_effect = [
            handle_wf1,
            handle_wf2,
        ]
        env = ActivityEnvironment()
        param = CancelObsoleteDownloadWorkflowsParam(sha_to_download=shas)
        await env.run(
            boot_activities.cancel_obsolete_download_workflows, param
        )

        mock_temporal_client.list_workflows.assert_called_once_with(
            query=f"WorkflowType='{SYNC_BOOTRESOURCES_WORKFLOW_NAME}' AND ExecutionStatus='Running'"
        )

        mock_temporal_client.get_workflow_handle.assert_has_calls(
            [
                call(wf1.id),
                call(wf2.id),
            ]
        )

        handle_wf1.cancel.assert_awaited_once()
        handle_wf2.cancel.assert_awaited_once()


class MockActivities:
    def __init__(self):
        self.disk_space_result = True
        self.endpoints_result = {
            "abcdef": ["http://10.0.0.1:5240/MAAS/boot-resources/"],
            "ghijkl": ["http://10.0.0.2:5240/MAAS/boot-resources/"],
            "mnopqr": ["http://10.0.0.3:5240/MAAS/boot-resources/"],
        }
        self.download_result = True
        self.synced_regions_result = ["abcdef"]
        self.files_to_download_result = GetFilesToDownloadReturnValue(
            resources=[
                ResourceDownloadParam(
                    rfile_ids=[1],
                    source_list=["http://maas-image-stream.io"],
                    sha256="0" * 64,
                    filename_on_disk="0" * 7,
                    total_size=100,
                )
            ],
            boot_resource_ids={1, 2, 3},
        )

    @activity.defn(name=CHECK_DISK_SPACE_ACTIVITY_NAME)
    async def check_disk_space(self, param: SpaceRequirementParam) -> bool:
        return self.disk_space_result

    @activity.defn(name=GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME)
    async def get_bootresourcefile_endpoints(self) -> dict[str, list]:
        return self.endpoints_result

    @activity.defn(name=DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME)
    async def download_bootresourcefile(
        self, param: ResourceDownloadParam
    ) -> bool:
        return self.download_result

    @activity.defn(name=GET_SYNCED_REGIONS_ACTIVITY_NAME)
    async def get_synced_regions_for_files(
        self, file_ids: set[int]
    ) -> list[str]:
        return self.synced_regions_result

    @activity.defn(name=GET_FILES_TO_DOWNLOAD_ACTIVITY_NAME)
    async def get_files_to_download(self) -> GetFilesToDownloadReturnValue:
        return self.files_to_download_result

    @activity.defn(name=CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME)
    async def cleanup_old_boot_resources(
        self, param: CleanupOldBootResourceParam
    ) -> None:
        pass

    @activity.defn(name=CANCEL_OBSOLETE_DOWNLOAD_WORKFLOWS_ACTIVITY_NAME)
    async def cancel_obsolete_download_workflows(
        self, param: CancelObsoleteDownloadWorkflowsParam
    ) -> None:
        pass

    @activity.defn(name=SET_GLOBAL_DEFAULT_RELEASES_ACTIVITY_NAME)
    async def set_global_default_releases(self) -> None:
        pass


@pytest.fixture
def sample_endpoints_single_region():
    """Single region endpoint configuration"""
    return {"abcdef": ["http://10.0.0.1:5240/MAAS/boot-resources/"]}


@pytest.fixture
def sample_endpoints_three_regions():
    """Three region endpoint configuration"""
    return {
        "abcdef": ["http://10.0.0.1:5240/MAAS/boot-resources/"],
        "ghijkl": ["http://10.0.0.2:5240/MAAS/boot-resources/"],
        "mnopqr": ["http://10.0.0.3:5240/MAAS/boot-resources/"],
    }


@pytest.fixture
def sample_resource():
    """Sample ResourceDownloadParam"""
    return ResourceDownloadParam(
        rfile_ids=[1],
        source_list=["http://maas-image-stream.io"],
        sha256="0" * 64,
        filename_on_disk="0" * 7,
        total_size=100,
    )


@pytest.fixture
def sample_sync_request_single(
    sample_resource, sample_endpoints_single_region
):
    """Sample SyncRequestParam for single region"""
    return SyncRequestParam(
        resource=sample_resource, endpoints=sample_endpoints_single_region
    )


@pytest.fixture
def sample_sync_request_three(sample_resource, sample_endpoints_three_regions):
    """Sample SyncRequestParam for three regions"""
    return SyncRequestParam(
        resource=sample_resource, endpoints=sample_endpoints_three_regions
    )


@pytest.fixture
def mock_activities():
    return MockActivities()


class TestSyncBootResourcesWorkflow:
    @pytest.mark.asyncio
    async def test_single_region_sync_signals_master(
        self, sample_sync_request_single, mock_activities
    ):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            mock_handle = AsyncMock()
            mock_handle.signal = AsyncMock()

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[SyncBootResourcesWorkflow],
                activities=[
                    mock_activities.download_bootresourcefile,
                    mock_activities.get_synced_regions_for_files,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ) as mock_child,
                    patch(
                        "temporalio.workflow.get_external_workflow_handle_for",
                        return_value=mock_handle,
                    ),
                ):
                    await env.client.execute_workflow(
                        SyncBootResourcesWorkflow.run,
                        sample_sync_request_single,
                        id="test-sync-single",
                        task_queue="test-queue",
                    )

                    mock_child.assert_called_once()

                    mock_handle.signal.assert_called_once_with(
                        MasterImageSyncWorkflow.file_completed_download,
                        sample_sync_request_single.resource.sha256,
                    )

    @pytest.mark.asyncio
    async def test_three_region_sync_with_missing_regions(
        self, sample_sync_request_three, mock_activities
    ):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            # Only one synced region
            mock_activities.synced_regions_result = ["abcdef"]

            mock_handle = AsyncMock()
            mock_handle.signal = AsyncMock()

            future = asyncio.Future()
            future.set_result([True, True])
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[SyncBootResourcesWorkflow],
                activities=[
                    mock_activities.download_bootresourcefile,
                    mock_activities.get_synced_regions_for_files,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ) as mock_child,
                    patch(
                        "temporalio.workflow.get_external_workflow_handle_for",
                        return_value=mock_handle,
                    ),
                    patch(
                        "asyncio.gather", return_value=future
                    ) as mock_gather,
                ):
                    await env.client.execute_workflow(
                        SyncBootResourcesWorkflow.run,
                        sample_sync_request_three,
                        id="test-sync-three",
                        task_queue="test-queue",
                    )

                    # one for each region
                    assert mock_child.call_count == 3
                    # Should call gather for sync jobs (2 missing regions)
                    mock_gather.assert_called_once()

                    # Should signal completion
                    mock_handle.signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_upstream_download(
        self, sample_sync_request_single, mock_activities
    ):
        """Test workflow fails when upstream download fails"""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[SyncBootResourcesWorkflow],
                activities=[mock_activities.download_bootresourcefile],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=False,
                    ) as mock_child,
                    pytest.raises(WorkflowFailureError) as exc_info,
                ):
                    await env.client.execute_workflow(
                        SyncBootResourcesWorkflow.run,
                        sample_sync_request_single,
                        id="test-failed-download",
                        task_queue="test-queue",
                    )

                    mock_child.assert_called_once()
                    # The exception returned is WorkflowFailureError.
                    # The ApplicationError we raise is available in the `cause` attribute.
                    assert (
                        "could not be downloaded"
                        in exc_info.value.cause.message
                    )
                    assert exc_info.value.cause.non_retryable

    @pytest.mark.asyncio
    async def test_failed_sync_to_regions(
        self, sample_sync_request_three, mock_activities
    ):
        """Test workflow fails when sync to other regions fails"""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            mock_activities.synced_regions_result = ["abcdef"]
            mock_handle = AsyncMock()
            future = asyncio.Future()
            future.set_result([True, False])  # One sync fails

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[SyncBootResourcesWorkflow],
                activities=[
                    mock_activities.download_bootresourcefile,
                    mock_activities.get_synced_regions_for_files,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ) as mock_child,
                    patch(
                        "temporalio.workflow.get_external_workflow_handle_for",
                        return_value=mock_handle,
                    ),
                    patch("asyncio.gather", return_value=future),
                    pytest.raises(WorkflowFailureError) as exc_info,
                ):
                    await env.client.execute_workflow(
                        SyncBootResourcesWorkflow.run,
                        sample_sync_request_three,
                        id="test-failed-sync",
                        task_queue="test-queue",
                    )

                    # one for each region
                    assert mock_child.call_count == 3
                    # The exception returned is WorkflowFailureError.
                    # The ApplicationError we raise is available in the `cause` attribute.
                    assert "could not be synced" in str(
                        exc_info.value.cause.message
                    )
                    assert exc_info.value.cause.non_retryable

    @pytest.mark.asyncio
    async def test_no_synced_regions_available(
        self, sample_sync_request_three, mock_activities
    ):
        """Test workflow fails when no regions have the complete file"""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            mock_activities.synced_regions_result = []  # No regions have the file

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[SyncBootResourcesWorkflow],
                activities=[
                    mock_activities.download_bootresourcefile,
                    mock_activities.get_synced_regions_for_files,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ),
                    pytest.raises(WorkflowFailureError) as exc_info,
                ):
                    await env.client.execute_workflow(
                        SyncBootResourcesWorkflow.run,
                        sample_sync_request_three,
                        id="test-no-synced-regions",
                        task_queue="test-queue",
                    )

                    # The exception returned is WorkflowFailureError.
                    # The ApplicationError we raise is available in the `cause` attribute.
                    assert "has no complete copy available" in str(
                        exc_info.value.cause.message
                    )
                    assert not exc_info.value.cause.non_retryable


class TestMasterImageSyncWorkflow:
    """Tests for MasterImageSyncWorkflow"""

    @pytest.mark.asyncio
    async def test_single_region_master_workflow(
        self, sample_endpoints_single_region, mock_activities
    ):
        """Test master workflow with single region"""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            mock_activities.endpoints_result = sample_endpoints_single_region

            check_disk_space_future = asyncio.Future()
            check_disk_space_future.set_result([True])
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[MasterImageSyncWorkflow],
                activities=[
                    mock_activities.get_files_to_download,
                    mock_activities.get_bootresourcefile_endpoints,
                    mock_activities.check_disk_space,
                    mock_activities.cancel_obsolete_download_workflows,
                    mock_activities.set_global_default_releases,
                    mock_activities.cleanup_old_boot_resources,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ) as mock_execute_child,
                    patch(
                        "temporalio.workflow.start_child_workflow"
                    ) as mock_start_child,
                    patch(
                        "asyncio.gather", return_value=check_disk_space_future
                    ),
                    patch("temporalio.workflow.wait_condition") as mock_wait,
                ):
                    await env.client.execute_workflow(
                        MasterImageSyncWorkflow.run,
                        id="test-master-single",
                        task_queue="test-queue",
                    )

                    # Check disk space for single region
                    assert mock_execute_child.call_count == 1
                    mock_wait.assert_awaited_once()
                    # Start sync workflow
                    mock_start_child.assert_called_once()

    @pytest.mark.asyncio
    async def test_three_region_master_workflow(
        self, sample_endpoints_three_regions, mock_activities
    ):
        """Test master workflow schedules sync for all regions"""
        async with await WorkflowEnvironment.start_time_skipping() as env:
            mock_activities.endpoints_result = sample_endpoints_three_regions

            check_disk_space_future = asyncio.Future()
            check_disk_space_future.set_result([True, True, True])
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[MasterImageSyncWorkflow],
                activities=[
                    mock_activities.get_files_to_download,
                    mock_activities.get_bootresourcefile_endpoints,
                    mock_activities.check_disk_space,
                    mock_activities.cancel_obsolete_download_workflows,
                    mock_activities.set_global_default_releases,
                    mock_activities.cleanup_old_boot_resources,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ) as mock_execute_child,
                    patch(
                        "temporalio.workflow.start_child_workflow"
                    ) as mock_start_child,
                    patch(
                        "asyncio.gather",
                        return_value=check_disk_space_future,
                    ),
                    patch("temporalio.workflow.wait_condition") as mock_wait,
                ):
                    await env.client.execute_workflow(
                        MasterImageSyncWorkflow.run,
                        id="test-master-three",
                        task_queue="test-queue",
                    )

                    # Check disk space for all 3 regions
                    assert mock_execute_child.call_count == 3
                    mock_wait.assert_awaited_once()

                    # Start sync workflow for one resource
                    mock_start_child.assert_called_once()

    @pytest.mark.asyncio
    async def test_insufficient_disk_space(
        self, sample_endpoints_three_regions, mock_activities
    ):
        async with await WorkflowEnvironment.start_time_skipping() as env:
            mock_activities.endpoints_result = sample_endpoints_three_regions
            check_disk_space_future = asyncio.Future()
            # One region has insufficient space
            check_disk_space_future.set_result([True, True, False])

            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[MasterImageSyncWorkflow],
                activities=[
                    mock_activities.get_files_to_download,
                    mock_activities.get_bootresourcefile_endpoints,
                    mock_activities.check_disk_space,
                    mock_activities.cancel_obsolete_download_workflows,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=False,
                    ) as mock_execute_child,
                    patch(
                        "asyncio.gather",
                        return_value=check_disk_space_future,
                    ),
                    pytest.raises(WorkflowFailureError) as exc_info,
                ):
                    await env.client.execute_workflow(
                        MasterImageSyncWorkflow.run,
                        id="test-insufficient-space",
                        task_queue="test-queue",
                    )

                    assert mock_execute_child.call_count == 3
                    assert "don't have enough disk space" in str(
                        exc_info.value.cause.message
                    )
                    assert exc_info.value.cause.non_retryable

    @pytest.mark.asyncio
    async def test_already_started_workflow_handling(
        self, sample_endpoints_single_region, mock_activities
    ):
        """Test workflow handles already started child workflows gracefully"""
        check_disk_space_future = asyncio.Future()
        check_disk_space_future.set_result([True])
        mock_activities.endpoints_result = sample_endpoints_single_region

        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with Worker(
                env.client,
                task_queue="test-queue",
                workflows=[MasterImageSyncWorkflow],
                activities=[
                    mock_activities.get_files_to_download,
                    mock_activities.get_bootresourcefile_endpoints,
                    mock_activities.check_disk_space,
                    mock_activities.cancel_obsolete_download_workflows,
                    mock_activities.set_global_default_releases,
                    mock_activities.cleanup_old_boot_resources,
                ],
            ):
                with (
                    patch(
                        "temporalio.workflow.execute_child_workflow",
                        return_value=True,
                    ),
                    patch(
                        "temporalio.workflow.start_child_workflow",
                        side_effect=WorkflowAlreadyStartedError(
                            workflow_id="test-already-started",
                            workflow_type=MASTER_IMAGE_SYNC_WORKFLOW_NAME,
                        ),
                    ) as mock_start,
                    patch(
                        "asyncio.gather", return_value=check_disk_space_future
                    ),
                    patch("temporalio.workflow.wait_condition"),
                ):
                    # Should not raise error
                    await env.client.execute_workflow(
                        MasterImageSyncWorkflow.run,
                        id="test-already-started",
                        task_queue="test-queue",
                    )

                    # Verify start_child_workflow was called
                    mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_signal_handling_removes_files(self):
        """Test that file_completed_download signal correctly removes files from tracking"""
        workflow_instance = MasterImageSyncWorkflow()
        workflow_instance._files_to_download = {"file1", "file2", "file3"}

        # Signal completion of file1
        await workflow_instance.file_completed_download("file1")
        assert "file1" not in workflow_instance._files_to_download
        assert workflow_instance._files_to_download == {"file2", "file3"}

        # Signal completion of non-existent file
        await workflow_instance.file_completed_download("nonexistent")
        assert workflow_instance._files_to_download == {"file2", "file3"}

        # Signal completion of remaining files
        await workflow_instance.file_completed_download("file2")
        await workflow_instance.file_completed_download("file3")
        assert workflow_instance._files_to_download == set()
