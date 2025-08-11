#  Copyright 2024-2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import shutil
from typing import Any, Coroutine

from aiohttp.client_exceptions import ClientError
from temporalio import activity, workflow
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ApplicationError, WorkflowAlreadyStartedError
from temporalio.workflow import (
    ActivityCancellationType,
    ChildWorkflowHandle,
    ParentClosePolicy,
    random,
)

from maascommon.workflows.bootresource import (
    CancelObsoleteDownloadWorkflowsParam,
    CHECK_BOOTRESOURCES_STORAGE_WORKFLOW_NAME,
    CLEANUP_TIMEOUT,
    CleanupOldBootResourceParam,
    DELETE_BOOTRESOURCE_WORKFLOW_NAME,
    DISK_TIMEOUT,
    DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
    DOWNLOAD_TIMEOUT,
    FETCH_IMAGE_METADATA_TIMEOUT,
    GetFilesToDownloadReturnValue,
    HEARTBEAT_TIMEOUT,
    MASTER_IMAGE_SYNC_WORKFLOW_NAME,
    MAX_SOURCES,
    REPORT_INTERVAL,
    ResourceDeleteParam,
    ResourceDownloadParam,
    SpaceRequirementParam,
    SYNC_BOOTRESOURCES_WORKFLOW_NAME,
    SyncRequestParam,
)
from maasserver.utils.converters import human_readable_bytes
from maasservicelayer.models.configurations import MAASUrlConfig
from maasservicelayer.utils.image_local_files import (
    get_bootresource_store_path,
    LocalBootResourceFile,
    LocalStoreInvalidHash,
    LocalStoreWriteBeyondEOF,
)
from maastemporalworker.worker import REGION_TASK_QUEUE
from maastemporalworker.workflow.activity import ActivityBase
from maastemporalworker.workflow.api_client import MAASAPIClient
from maastemporalworker.workflow.utils import (
    activity_defn_with_context,
    workflow_run_with_context,
)
from provisioningserver.utils.url import compose_URL

CHECK_DISK_SPACE_ACTIVITY_NAME = "check-disk-space"
GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME = "get-bootresourcefile-endpoints"
DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME = "download-bootresourcefile"
DELETE_BOOTRESOURCEFILE_ACTIVITY_NAME = "delete-bootresourcefile"
GET_FILES_TO_DOWNLOAD_ACTIVITY_NAME = "get-files-to-download"
CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME = "cleanup-old-boot-resources"
CANCEL_OBSOLETE_DOWNLOAD_WORKFLOWS_ACTIVITY_NAME = (
    "cancel-obsolete-download-workflows"
)
GET_SYNCED_REGIONS_ACTIVITY_NAME = "get-synced-regions"
SET_GLOBAL_DEFAULT_RELEASES_ACTIVITY_NAME = "set-global-default-releases"


class BootResourcesActivity(ActivityBase):
    async def init(self, region_id: str):
        self.region_id = region_id
        async with self.start_transaction() as services:
            maas_url = await services.configurations.get(MAASUrlConfig.name)
            token = await services.users.get_MAAS_user_apikey()
            user_agent = await services.configurations.get_maas_user_agent()
            self.apiclient = MAASAPIClient(
                url=maas_url, token=token, user_agent=user_agent
            )

    async def report_progress(self, rfiles: list[int], size: int):
        """Report progress back to MAAS

        Args:
            rfiles (list[int]): BootResourceFile ids
            size (int): current size, in bytes

        Returns:
           requests.Response: Response object
        """
        url = f"{self.apiclient.url}/api/2.0/images-sync-progress/"
        return await self.apiclient.request_async(
            "POST",
            url,
            data={
                "system_id": self.region_id,
                "ids": rfiles,
                "size": size,
            },
        )

    @activity_defn_with_context(name=CHECK_DISK_SPACE_ACTIVITY_NAME)
    async def check_disk_space(self, param: SpaceRequirementParam) -> bool:
        target_dir = get_bootresource_store_path()
        _, _, free = shutil.disk_usage(target_dir)
        if param.total_resources_size:
            free += sum(file.stat().st_size for file in target_dir.rglob("*"))
            required = param.total_resources_size
        else:
            required = param.min_free_space
        if free > required:
            return True
        else:
            activity.logger.error(
                f"Not enough disk space at controller '{self.region_id}', needs "
                f"{human_readable_bytes(required)} to store all resources."
            )
            return False

    @activity_defn_with_context(name=GET_SYNCED_REGIONS_ACTIVITY_NAME)
    async def get_synced_regions_for_files(
        self, file_ids: set[int]
    ) -> list[str]:
        async with self.start_transaction() as services:
            return await services.boot_resource_file_sync.get_synced_regions(
                file_ids
            )

    @activity_defn_with_context(
        name=GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME
    )
    async def get_bootresourcefile_endpoints(self) -> dict[str, list]:
        url = f"{self.apiclient.url}/api/2.0/regioncontrollers/"
        regions = await self.apiclient.request_async("GET", url)
        regions_endpoints = {}
        for region in regions:
            # https://bugs.launchpad.net/maas/+bug/2058037
            if region["ip_addresses"]:
                regions_endpoints[region["system_id"]] = [
                    compose_URL("http://:5240/MAAS/boot-resources/", src)
                    for src in region["ip_addresses"]
                ]
            else:
                raise ApplicationError(
                    f"Could not retrieve the IP addresses of the region controller '{region['system_id']}' from the API. This "
                    f"activity will be retried until we have the IP for all the region controllers.",
                    non_retryable=False,
                )
        return regions_endpoints

    @activity_defn_with_context(name=DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME)
    async def download_bootresourcefile(
        self, param: ResourceDownloadParam
    ) -> bool:
        """downloads boot resource file

        Returns:
            bool: True if the file was successfully downloaded
        """
        lfile = LocalBootResourceFile(
            param.sha256, param.filename_on_disk, param.total_size, param.size
        )

        url = param.source_list[
            activity.info().attempt % len(param.source_list)
        ]
        activity.logger.debug(f"Downloading from {url}")

        try:
            while not lfile.acquire_lock(try_lock=True):
                activity.heartbeat("Waiting for file lock")
                await asyncio.sleep(5)

            if await lfile.avalid():
                activity.logger.info("file already downloaded, skipping")
                lfile.commit()
                for target in param.extract_paths:
                    lfile.extract_file(target)
                    activity.heartbeat(f"Extracted file in {target}")
                await self.report_progress(param.rfile_ids, lfile.size)
                return True

            async with (
                self.apiclient.session.get(
                    url,
                    verify_ssl=False,
                    chunked=True,
                    proxy=param.http_proxy,
                ) as response,
                lfile.astore(autocommit=False) as store,
            ):
                response.raise_for_status()
                last_update = datetime.now(timezone.utc)
                async for data, _ in response.content.iter_chunks():
                    activity.heartbeat("Downloaded chunk")
                    store.write(data)
                    dt_now = datetime.now(timezone.utc)
                    if dt_now > (last_update + REPORT_INTERVAL):
                        await self.report_progress(param.rfile_ids, lfile.size)
                        last_update = dt_now

            activity.logger.debug("Download done, doing checksum")
            activity.heartbeat("Finished download, doing checksum")
            if await lfile.avalid():
                lfile.commit()
                activity.logger.debug(f"file commited {lfile.size}")

                for target in param.extract_paths:
                    lfile.extract_file(target)
                    activity.heartbeat(f"Extracted file in {target}")

                await self.report_progress(param.rfile_ids, lfile.size)
                return True
            else:
                await self.report_progress(param.rfile_ids, 0)
                lfile.unlink()
                raise ApplicationError("Invalid checksum")
        except IOError as ex:
            # if we run out of disk space, stop this download.
            # let the user fix the issue and restart it manually later
            if ex.errno == 28:
                lfile.unlink()
                await self.report_progress(param.rfile_ids, 0)
                activity.logger.error(ex.strerror)
                return False

            raise ApplicationError(
                ex.strerror, type=ex.__class__.__name__
            ) from None
        except (
            ClientError,
            LocalStoreInvalidHash,
            LocalStoreWriteBeyondEOF,
        ) as ex:
            raise ApplicationError(
                str(ex), type=ex.__class__.__name__
            ) from None
        finally:
            lfile.release_lock()

    @activity_defn_with_context(name=DELETE_BOOTRESOURCEFILE_ACTIVITY_NAME)
    async def delete_bootresourcefile(
        self, param: ResourceDeleteParam
    ) -> bool:
        """Delete files from disk"""
        for file in param.files:
            activity.logger.debug(f"attempt to delete {file}")
            lfile = LocalBootResourceFile(
                file.sha256, file.filename_on_disk, 0
            )
            try:
                while not lfile.acquire_lock(try_lock=True):
                    activity.heartbeat("Waiting for file lock")
                    await asyncio.sleep(5)
                lfile.unlink()
            finally:
                lfile.release_lock()
            activity.logger.info(f"file {file} deleted")
        return True

    @activity_defn_with_context(name=GET_FILES_TO_DOWNLOAD_ACTIVITY_NAME)
    async def get_files_to_download(self) -> GetFilesToDownloadReturnValue:
        resources_to_download: dict[str, ResourceDownloadParam] = {}
        boot_resource_ids_to_keep: set[int] = set()
        async with self.start_transaction() as services:
            boot_source_products_mapping = (
                await services.image_sync.fetch_images_metadata()
            )
            for (
                boot_source,
                products_list,
            ) in boot_source_products_mapping.items():
                await services.image_sync.cache_boot_source_from_simplestreams_products(
                    boot_source.id, products_list
                )

            await services.image_sync.sync_boot_source_selections_from_msm(
                list(boot_source_products_mapping.keys())
            )

            if not await services.image_sync.check_commissioning_series_selected():
                raise ApplicationError(
                    "Either the commissioning os or the commissioning series "
                    "are not selected or are not available in the stream.",
                    non_retryable=True,
                )

            boot_source_products_mapping = (
                await services.image_sync.filter_products(
                    boot_source_products_mapping
                )
            )
            for (
                boot_source,
                products_list,
            ) in boot_source_products_mapping.items():
                (
                    to_download,
                    boot_resource_ids,
                ) = await services.image_sync.get_files_to_download_from_product_list(
                    boot_source, products_list
                )
                resources_to_download.update(to_download)
                boot_resource_ids_to_keep |= boot_resource_ids

        return GetFilesToDownloadReturnValue(
            resources=list(resources_to_download.values()),
            boot_resource_ids=boot_resource_ids_to_keep,
        )

    @activity_defn_with_context(name=SET_GLOBAL_DEFAULT_RELEASES_ACTIVITY_NAME)
    async def set_global_default_releases(self) -> None:
        async with self.start_transaction() as services:
            await services.image_sync.set_global_default_releases()

    @activity_defn_with_context(name=CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME)
    async def cleanup_old_boot_resources(
        self, param: CleanupOldBootResourceParam
    ) -> None:
        async with self.start_transaction() as services:
            await services.image_sync.delete_old_boot_resources(
                param.boot_resource_ids_to_keep
            )
            await services.image_sync.delete_old_boot_resource_sets()

    @activity_defn_with_context(
        name=CANCEL_OBSOLETE_DOWNLOAD_WORKFLOWS_ACTIVITY_NAME
    )
    async def cancel_obsolete_download_workflows(
        self, param: CancelObsoleteDownloadWorkflowsParam
    ) -> None:
        shas_to_download = {sha[:12] for sha in param.sha_to_download}
        async for wf in self.temporal_client.list_workflows(
            query=f"WorkflowType='{SYNC_BOOTRESOURCES_WORKFLOW_NAME}' AND ExecutionStatus='Running'"
        ):
            # Workflow ID is in the form: <wf-name>:<sha>
            sha = wf.id.rsplit(":", maxsplit=1)[1]
            if sha not in shas_to_download:
                handle = self.temporal_client.get_workflow_handle(wf.id)
                await handle.cancel()


@workflow.defn(name=DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME, sandboxed=False)
class DownloadBootResourceWorkflow:
    """Downloads a BootResourceFile to this controller"""

    @workflow_run_with_context
    async def run(self, input: ResourceDownloadParam) -> bool:
        return await workflow.execute_activity(
            DOWNLOAD_BOOTRESOURCEFILE_ACTIVITY_NAME,
            input,
            start_to_close_timeout=DOWNLOAD_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            cancellation_type=ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
            retry_policy=RetryPolicy(
                maximum_attempts=0,  # No maximum attempts
                maximum_interval=timedelta(seconds=60),
            ),
        )


@workflow.defn(name=CHECK_BOOTRESOURCES_STORAGE_WORKFLOW_NAME, sandboxed=False)
class CheckBootResourcesStorageWorkflow:
    """Check the BootResource Storage on this controller"""

    @workflow_run_with_context
    async def run(self, input: SpaceRequirementParam) -> None:
        return await workflow.execute_activity(
            CHECK_DISK_SPACE_ACTIVITY_NAME,
            input,
            start_to_close_timeout=DISK_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_TIMEOUT,
            cancellation_type=ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )


@workflow.defn(name=SYNC_BOOTRESOURCES_WORKFLOW_NAME, sandboxed=False)
class SyncBootResourcesWorkflow:
    """Execute Boot Resource synchronization from external sources"""

    @workflow_run_with_context
    async def run(self, input: SyncRequestParam) -> None:
        def _schedule_download(
            res: ResourceDownloadParam,
            region: str | None = None,
        ) -> Coroutine[Any, Any, bool]:
            return workflow.execute_child_workflow(
                DOWNLOAD_BOOTRESOURCE_WORKFLOW_NAME,
                res,
                id=f"download-bootresource:{region or 'upstream'}:{res.sha256[:12]}",
                execution_timeout=DOWNLOAD_TIMEOUT,
                run_timeout=DOWNLOAD_TIMEOUT,
                task_queue=f"region:{region}" if region else REGION_TASK_QUEUE,
            )

        # download resource from upstream
        downloaded = await _schedule_download(input.resource)
        if not downloaded:
            raise ApplicationError(
                f"File {input.resource.sha256} could not be downloaded, aborting",
                non_retryable=True,
            )

        handle = workflow.get_external_workflow_handle_for(
            MasterImageSyncWorkflow.run, "master-download-bootresource"
        )

        regions = frozenset(input.endpoints.keys())

        if len(regions) < 2:
            workflow.logger.info(
                f"Sync complete for file {input.resource.sha256}"
            )
            await handle.signal(
                MasterImageSyncWorkflow.file_completed_download,
                input.resource.sha256,
            )
            return

        # sync the resource with the other regions
        synced_regions: list[str] = await workflow.execute_activity(
            GET_SYNCED_REGIONS_ACTIVITY_NAME,
            arg={file_id for file_id in input.resource.rfile_ids},
            start_to_close_timeout=timedelta(seconds=30),
        )

        if not synced_regions:
            raise ApplicationError(
                f"File {input.resource.sha256} has no complete copy available"
            )

        missing_regions = regions - set(synced_regions)

        # Use a random generator from the temporal sdk in order to keep the workflow deterministic.
        random_generator = random()

        eps = [
            f"{endpoint}{input.resource.filename_on_disk}/"
            for region in synced_regions
            for endpoint in input.endpoints[region]
        ]
        # In order to balance the workload on the regions we randomize the order of the source_list.
        new_res = replace(
            input.resource,
            source_list=random_generator.sample(
                eps, min(len(eps), MAX_SOURCES)
            ),
        )
        sync_jobs = [
            _schedule_download(new_res, region) for region in missing_regions
        ]

        if sync_jobs:
            synced = await asyncio.gather(*sync_jobs)
            if not all(synced):
                raise ApplicationError(
                    f"File {input.resource.sha256} could not be synced, aborting",
                    non_retryable=True,
                )

        await handle.signal(
            MasterImageSyncWorkflow.file_completed_download,
            input.resource.sha256,
        )
        workflow.logger.info(f"Sync complete for file {input.resource.sha256}")


@workflow.defn(name=DELETE_BOOTRESOURCE_WORKFLOW_NAME, sandboxed=False)
class DeleteBootResourceWorkflow:
    """Delete a BootResourceFile from this cluster"""

    @workflow_run_with_context
    async def run(self, input: ResourceDeleteParam) -> None:
        # remove file from cluster
        endpoints = await workflow.execute_activity(
            GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,
            start_to_close_timeout=timedelta(seconds=30),
        )
        regions = frozenset(endpoints.keys())
        for r in regions:
            await workflow.execute_activity(
                DELETE_BOOTRESOURCEFILE_ACTIVITY_NAME,
                input,
                task_queue=f"region:{r}",
                start_to_close_timeout=DISK_TIMEOUT,
                schedule_to_close_timeout=DISK_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=3),
            )


@workflow.defn(name=MASTER_IMAGE_SYNC_WORKFLOW_NAME, sandboxed=False)
class MasterImageSyncWorkflow:
    def __init__(self) -> None:
        # list of sha256 that must be downloaded
        self._files_to_download: set[str] = set()

    def _schedule_disk_check(
        self,
        res: SpaceRequirementParam,
        region: str,
    ):
        return workflow.execute_child_workflow(
            CHECK_BOOTRESOURCES_STORAGE_WORKFLOW_NAME,
            res,
            id=f"check-bootresources-storage:{region}",
            execution_timeout=DISK_TIMEOUT,
            run_timeout=DISK_TIMEOUT,
            id_reuse_policy=WorkflowIDReusePolicy.TERMINATE_IF_RUNNING,
            task_queue=f"region:{region}",
        )

    def _download_and_sync_resource(
        self,
        input: SyncRequestParam,
    ) -> Coroutine[Any, Any, ChildWorkflowHandle]:
        wf_id = f"sync-bootresource:{input.resource.sha256[:12]}"
        try:
            return workflow.start_child_workflow(
                SYNC_BOOTRESOURCES_WORKFLOW_NAME,
                input,
                id=wf_id,
                execution_timeout=DOWNLOAD_TIMEOUT,
                run_timeout=DOWNLOAD_TIMEOUT,
                parent_close_policy=ParentClosePolicy.ABANDON,
                task_queue=REGION_TASK_QUEUE,
            )
        except WorkflowAlreadyStartedError:
            workflow.logger.debug(
                f"Sync workflow with id {wf_id} already running. Skipping."
            )

    @workflow_run_with_context
    async def run(self) -> None:
        result = await workflow.execute_activity(
            GET_FILES_TO_DOWNLOAD_ACTIVITY_NAME,
            start_to_close_timeout=FETCH_IMAGE_METADATA_TIMEOUT,
        )

        resources_to_download = [
            ResourceDownloadParam(**res) for res in result["resources"]
        ]
        boot_resource_ids_to_keep = result["boot_resource_ids"]

        required_disk_space_for_files = sum(
            [r.total_size for r in resources_to_download],
            start=100 * 2**20,  # space to uncompress the bootloaders
        )
        # get regions and endpoints
        endpoints = await workflow.execute_activity(
            GET_BOOTRESOURCEFILE_ENDPOINTS_ACTIVITY_NAME,
            start_to_close_timeout=timedelta(seconds=30),
        )
        regions: frozenset[str] = frozenset(endpoints.keys())

        self._files_to_download = set(
            res.sha256 for res in resources_to_download
        )

        # check disk space
        check_space_jobs = [
            self._schedule_disk_check(
                SpaceRequirementParam(
                    total_resources_size=required_disk_space_for_files
                ),
                region,
            )
            for region in regions
        ]
        has_space: list[bool] = await asyncio.gather(*check_space_jobs)
        if not all(has_space):
            raise ApplicationError(
                "some region controllers don't have enough disk space",
                non_retryable=True,
            )

        # cancel obsolete download workflows that are running
        await workflow.execute_activity(
            CANCEL_OBSOLETE_DOWNLOAD_WORKFLOWS_ACTIVITY_NAME,
            arg=CancelObsoleteDownloadWorkflowsParam(self._files_to_download),
            start_to_close_timeout=timedelta(seconds=30),
        )

        sync_jobs = [
            self._download_and_sync_resource(
                SyncRequestParam(resource=res, endpoints=endpoints)
            )
            for res in resources_to_download
        ]

        if sync_jobs:
            workflow.logger.info(
                f"Syncing {len(sync_jobs)} resources from upstream"
            )
            await asyncio.gather(*sync_jobs)

        await workflow.wait_condition(lambda: self._files_to_download == set())

        await workflow.execute_activity(
            SET_GLOBAL_DEFAULT_RELEASES_ACTIVITY_NAME,
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.execute_activity(
            CLEANUP_OLD_BOOT_RESOURCES_ACTIVITY_NAME,
            arg=CleanupOldBootResourceParam(boot_resource_ids_to_keep),
            start_to_close_timeout=CLEANUP_TIMEOUT,
        )

    @workflow.signal
    async def file_completed_download(self, sha256: str) -> None:
        """Signal handler for when a sync workflow has been completed."""
        try:
            self._files_to_download.remove(sha256)
        except KeyError:
            # KeyError can happen if the signal is sent when the MasterWorkflow has
            # been restarted but it hasn't populated the files yet.
            pass
