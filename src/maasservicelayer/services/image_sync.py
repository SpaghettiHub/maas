# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import re

import aiofiles
import aiofiles.os
from structlog import get_logger

from maascommon.constants import BOOTLOADERS_DIR
from maascommon.enums.boot_resources import (
    BootResourceFileType,
    BootResourceType,
)
from maascommon.enums.events import EventTypeEnum
from maascommon.enums.notifications import NotificationCategoryEnum
from maascommon.workflows.bootresource import ResourceDownloadParam
from maasservicelayer.builders.bootsourcecache import BootSourceCacheBuilder
from maasservicelayer.builders.notifications import NotificationBuilder
from maasservicelayer.context import Context
from maasservicelayer.db.filters import OrderByClauseFactory, QuerySpec
from maasservicelayer.db.repositories.bootresourcefiles import (
    BootResourceFileClauseFactory,
)
from maasservicelayer.db.repositories.bootresources import (
    BootResourceClauseFactory,
)
from maasservicelayer.db.repositories.bootresourcesets import (
    BootResourceSetClauseFactory,
    BootResourceSetsOrderByClauses,
)
from maasservicelayer.db.repositories.bootsourcecache import (
    BootSourceCacheClauseFactory,
)
from maasservicelayer.db.repositories.bootsourceselections import (
    BootSourceSelectionClauseFactory,
)
from maasservicelayer.models.bootresources import BootResource
from maasservicelayer.models.bootsourcecache import BootSourceCache
from maasservicelayer.models.bootsources import BootSource
from maasservicelayer.models.bootsourceselections import BootSourceSelection
from maasservicelayer.models.configurations import (
    BootImagesNoProxyConfig,
    CommissioningDistroSeriesConfig,
    CommissioningOSystemConfig,
    EnableHttpProxyConfig,
    HttpProxyConfig,
)
from maasservicelayer.services.base import Service, ServiceCache
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
from maasservicelayer.services.configurations import ConfigurationsService
from maasservicelayer.services.events import EventsService
from maasservicelayer.services.notifications import NotificationsService
from maasservicelayer.simplestreams.client import SimpleStreamsClient
from maasservicelayer.simplestreams.models import (
    BootloaderProduct,
    ImageProduct,
    MultiFileProduct,
    Product,
    SimpleStreamsProductList,
    SingleFileProduct,
)

logger = get_logger()

# duplicated from src/maassservicelayer/utils/images/repo_dumper

# Compile a regex to validate Ubuntu product names. This only allows V2 and V3
# Ubuntu images. "v3+platform" is intended for platform-optimised kernels.
UBUNTU_REGEX = re.compile(r".*:v([23]|3\+platform):.*", re.IGNORECASE)
# Compile a regex to validate bootloader product names. This only allows V1
# bootloaders.
BOOTLOADER_REGEX = re.compile(".*:1:.*", re.IGNORECASE)
# Validate MAAS supports the specific bootloader_type, os, arch
# combination.
SUPPORTED_BOOTLOADERS = {
    "pxe": [{"os": "pxelinux", "arch": "i386"}],
    "uefi": [
        {"os": "grub-efi-signed", "arch": "amd64"},
        {"os": "grub-efi", "arch": "arm64"},
    ],
    "open-firmware": [{"os": "grub-ieee1275", "arch": "ppc64el"}],
}


class ImageSyncService(Service):
    def __init__(
        self,
        context: Context,
        boot_sources_service: BootSourcesService,
        boot_source_cache_service: BootSourceCacheService,
        boot_source_selections_service: BootSourceSelectionsService,
        boot_resources_service: BootResourceService,
        boot_resource_sets_service: BootResourceSetsService,
        boot_resource_files_service: BootResourceFilesService,
        boot_resource_file_sync_service: BootResourceFileSyncService,
        events_service: EventsService,
        configurations_service: ConfigurationsService,
        notifications_service: NotificationsService,
        cache: ServiceCache | None = None,
    ):
        self.boot_sources_service = boot_sources_service
        self.boot_source_cache_service = boot_source_cache_service
        self.boot_source_selections_service = boot_source_selections_service
        self.boot_resources_service = boot_resources_service
        self.boot_resource_sets_service = boot_resource_sets_service
        self.boot_resource_files_service = boot_resource_files_service
        self.boot_resource_file_sync_service = boot_resource_file_sync_service
        self.events_service = events_service
        self.configurations_service = configurations_service
        self.notifications_service = notifications_service

        super().__init__(context, cache)

    async def sync_boot_source_selections_from_msm(self):
        # TODO
        raise NotImplementedError()

    async def _get_http_proxy(self) -> str | None:
        """Returns the http proxy to be used to download images metadata."""
        if not await self.configurations_service.get(
            EnableHttpProxyConfig.name
        ) or await self.configurations_service.get(
            BootImagesNoProxyConfig.name
        ):
            return None
        return await self.configurations_service.get(HttpProxyConfig.name)

    async def _write_keyring_data_to_tmp_file(
        self, keyring_data: bytes
    ) -> str:
        # write the keyring data to a temporary file
        async with aiofiles.tempfile.NamedTemporaryFile(
            delete=False
        ) as tmp_keyring_file:
            await tmp_keyring_file.write(keyring_data)
        return str(tmp_keyring_file.name)

    async def fetch_image_metadata(
        self,
        source_url: str,
        keyring_path: str | None = None,
        keyring_data: bytes | None = None,
    ) -> list[SimpleStreamsProductList]:
        http_proxy = await self._get_http_proxy()

        tmp_keyring_filename = None
        if keyring_data:
            tmp_keyring_filename = await self._write_keyring_data_to_tmp_file(
                keyring_data
            )
            keyring_file = tmp_keyring_filename
        else:
            keyring_file = keyring_path

        async with SimpleStreamsClient(
            url=source_url,
            http_proxy=http_proxy,
            keyring_file=str(keyring_file),
        ) as client:
            products_list = await client.get_all_products()

        if tmp_keyring_filename:
            await aiofiles.os.unlink(tmp_keyring_filename)

        return products_list

    async def fetch_images_metadata(
        self,
    ) -> dict[BootSource, list[SimpleStreamsProductList]]:
        """Fetch the images metadata from the simplestreams server for each boot source.

        For each boot source it will fetch the simplestreams data (based on the
        boot source url) using `SimpleStreamsClient`. If the boot source specifies
        keyring_data, it will write that into a temporary file.

        Returns:
            A dict mapping boot_sources to their corresponding simplestreams products.
        """
        boot_sources = await self.boot_sources_service.get_many(
            query=QuerySpec()
        )
        boot_source_products_mapping = {}

        http_proxy = await self._get_http_proxy()

        for boot_source in boot_sources:
            tmp_keyring_file_name = None
            if boot_source.keyring_data:
                tmp_keyring_file_name = (
                    await self._write_keyring_data_to_tmp_file(
                        boot_source.keyring_data
                    )
                )

                keyring_file = tmp_keyring_file_name
            else:
                keyring_file = boot_source.keyring_filename

            async with SimpleStreamsClient(
                url=boot_source.url,
                http_proxy=http_proxy,
                keyring_file=str(keyring_file),
                skip_pgp_verification=boot_source.skip_keyring_verification,
            ) as client:
                boot_source_products_mapping[
                    boot_source
                ] = await client.get_all_products()

            if tmp_keyring_file_name:
                await aiofiles.os.unlink(str(tmp_keyring_file_name))

        return boot_source_products_mapping

    async def cache_boot_source_from_simplestreams_products(
        self,
        boot_source_id: int,
        products_list: list[SimpleStreamsProductList],
    ) -> list[BootSourceCache]:
        """Update the boot source cache based on the simplestreams products_list.

        If the list of product is empty, delete the cache.

        Args:
            - boot_source_id: the boot source from where the simplestreams products come from
            - products_list: list of simplestreams products associated with the boot source

        Returns:
            A list of the new boot source caches.
        """
        boot_source_caches = []
        if len(products_list) == 0:
            await self.boot_source_cache_service.delete_many(
                query=QuerySpec(
                    where=BootSourceCacheClauseFactory.with_boot_source_id(
                        boot_source_id
                    )
                )
            )
            return []
        boot_source_cache_builders = set()
        for product_list in products_list:
            boot_source_cache_builders |= (
                BootSourceCacheBuilder.from_simplestreams_product_list(
                    product_list, boot_source_id
                )
            )

        for builder in boot_source_cache_builders:
            boot_source_caches.append(
                await self.boot_source_cache_service.create_or_update(builder)
            )

        # delete the old boot source caches, i.e. the ones that weren't created
        # or updated.
        await self.boot_source_cache_service.delete_many(
            query=QuerySpec(
                where=BootSourceCacheClauseFactory.and_clauses(
                    [
                        BootSourceCacheClauseFactory.with_boot_source_id(
                            boot_source_id
                        ),
                        BootSourceCacheClauseFactory.not_clause(
                            BootSourceCacheClauseFactory.with_ids(
                                {cache.id for cache in boot_source_caches}
                            )
                        ),
                    ]
                )
            )
        )
        return boot_source_caches

    async def check_commissioning_series_selected(self) -> None:
        """Creates an error notification if the commissioning os and the commissioning
        series are not in the selections or in the boot source cache.
        """
        commissioning_os = await self.configurations_service.get(
            CommissioningOSystemConfig.name
        )
        commissioning_series = await self.configurations_service.get(
            CommissioningDistroSeriesConfig.name
        )
        if not await self.boot_source_selections_service.exists(
            query=QuerySpec(
                where=BootSourceSelectionClauseFactory.and_clauses(
                    [
                        BootSourceSelectionClauseFactory.with_os(
                            commissioning_os
                        ),
                        BootSourceSelectionClauseFactory.with_release(
                            commissioning_series
                        ),
                    ]
                )
            )
        ):
            await self.notifications_service.create(
                NotificationBuilder(
                    ident="commissioning_series_unselected",
                    users=True,
                    admins=True,
                    message=f"{commissioning_os} {commissioning_series} is configured "
                    "as the commissioning release but it is not selected for download!",
                    context={},
                    user_id=None,
                    category=NotificationCategoryEnum.ERROR,
                    dismissable=True,
                )
            )
        if not await self.boot_source_cache_service.exists(
            query=QuerySpec(
                where=BootSourceCacheClauseFactory.and_clauses(
                    [
                        BootSourceCacheClauseFactory.with_os(commissioning_os),
                        BootSourceCacheClauseFactory.with_release(
                            commissioning_series
                        ),
                    ]
                )
            )
        ):
            await self.notifications_service.create(
                NotificationBuilder(
                    ident="commissioning_series_unavailable",
                    users=True,
                    admins=True,
                    message=f"{commissioning_os} {commissioning_series} is configured "
                    "as the commissioning release but it is unavailable in the "
                    "configured streams!",
                    context={},
                    user_id=None,
                    category=NotificationCategoryEnum.ERROR,
                    dismissable=True,
                )
            )

    def _bootloader_matches_selections(
        self, product: BootloaderProduct
    ) -> bool:
        if BOOTLOADER_REGEX.search(product.product_name) is None:
            # Only insert V1 bootloaders from the stream
            return False
        for bootloader in SUPPORTED_BOOTLOADERS.get(
            product.bootloader_type, []
        ):
            if (
                product.os == bootloader["os"]
                and product.arch == bootloader["arch"]
            ):
                return True
        return False

    def _image_product_matches_selections(
        self, product: ImageProduct, selections: list[BootSourceSelection]
    ) -> bool:
        for selection in selections:
            arches = selection.arches or []
            subarches = selection.subarches or []
            labels = selection.labels or []
            if (
                product.os == selection.os
                and product.release == selection.release
                and (product.arch in arches or arches == ["*"])
                and (product.subarch in subarches or subarches == ["*"])
                and (product.label in labels or labels == ["*"])
            ):
                return True
        return False

    def _single_file_image_matches_selections(
        self, product: SingleFileProduct, selections: list[BootSourceSelection]
    ) -> bool:
        return self._image_product_matches_selections(product, selections)

    def _multi_file_image_matches_selections(
        self, product: MultiFileProduct, selections: list[BootSourceSelection]
    ) -> bool:
        if UBUNTU_REGEX.search(product.product_name) is None:
            # Only insert v2 or v3 Ubuntu products.
            return False
        return self._image_product_matches_selections(product, selections)

    def product_matches_selections(
        self,
        product: Product,
        selections: list[BootSourceSelection],
    ) -> bool:
        """Whether `product` matches our boot source selections.

        It's used to filter only the products that we are interested in.

        Args:
            - product: the simplestreams product being evaluated
            - selections: list of boot source selections
        """
        match = False
        if isinstance(product, BootloaderProduct):
            match = self._bootloader_matches_selections(product)
        elif isinstance(product, SingleFileProduct):
            match = self._single_file_image_matches_selections(
                product, selections
            )
        elif isinstance(product, MultiFileProduct):
            match = self._multi_file_image_matches_selections(
                product, selections
            )
        return match

    async def filter_products(
        self,
        boot_source_products_mapping: dict[
            BootSource, list[SimpleStreamsProductList]
        ],
    ) -> dict[BootSource, list[SimpleStreamsProductList]]:
        """Filter simplestreams products to be downloaded.

        It takes into account both the selections and the priority of the boot source.
        It starts from the highest priority boot source and for each of them:
            - get the selections that apply to that boot source
            - for each product list in the mapping:
                - update the product list with the products that, at the same time,
                match the selections AND are not already added by another boot source
                - keep track of the already added products

        Args:
            - boot_source_products_mapping: a dict mapping a boot source to its
            simplestreams product list (see `fetch_images_metadata`)

        Returns:
            The initial dict containing, for each boot source, only the products
            that must be downloaded.

        """
        seen_products: set[Product] = set()

        sorted_boot_sources = sorted(
            boot_source_products_mapping.keys(),
            key=lambda boot_source: boot_source.priority,
            reverse=True,
        )

        selections = await self.boot_source_selections_service.get_many(
            query=QuerySpec()
        )

        for boot_source in sorted_boot_sources:
            selections_for_boot_source = [
                s for s in selections if s.boot_source_id == boot_source.id
            ]
            for product_list in boot_source_products_mapping[boot_source]:
                new_product_list = []
                for product in product_list.products:
                    if (
                        self.product_matches_selections(
                            product, selections_for_boot_source
                        )
                        and product not in seen_products
                    ):
                        new_product_list.append(product)
                        seen_products.add(product)

                product_list.products = new_product_list

        return boot_source_products_mapping

    async def get_files_to_download_from_product_list(
        self,
        boot_source: BootSource,
        filtered_products_list: list[SimpleStreamsProductList],
    ) -> tuple[dict[str, ResourceDownloadParam], set[int]]:
        """Get all the files that must be downloaded from simplestreams for this boot source.

        Args:
            - boot_source: The boot source
            - filtered_products_list: The filtered list of simplestreams products for this source

        Returns:
            A tuple (resources_to_download, boot_resource_ids) where resources_to_download
            is a dict mapping the sha256 to the corresponding ResourceDownloadParam
            (to be later supplied to the Temporal workflow) and boot_resource_ids
            is a set of the ids of the boot resources that have been used/created.
            The latter will come in handy when deleting the old boot resources.
        """
        resources_to_download: dict[str, ResourceDownloadParam] = {}
        boot_resource_ids = set()
        for product_list in filtered_products_list:
            for product in product_list.products:
                (
                    to_download,
                    boot_resource_id,
                ) = await self.get_files_to_download_from_product(
                    boot_source.url,
                    product,
                )
                for resource in to_download:
                    if existent := resources_to_download.get(resource.sha256):
                        # Multiple requests for the same SHA256 are combined in a single operation.
                        existent.rfile_ids.extend(resource.rfile_ids)
                        existent.source_list.extend(resource.source_list)
                        existent.extract_paths.extend(resource.extract_paths)

                    else:
                        resources_to_download[resource.sha256] = resource
                boot_resource_ids.add(boot_resource_id)

        return (resources_to_download, boot_resource_ids)

    async def get_files_to_download_from_product(
        self,
        boot_source_url: str,
        product: Product,
    ) -> tuple[list[ResourceDownloadParam], int]:
        """Returns the files to be downloaded from a simplestreams product.

        Filtering happens before this function. If we arrived here we have to
        download all the files from the product.

        Args:
            - boot_source_url: the URL of the boot source tied to this product
            - product: the simplestreams product to extract files from

        Returns:
            A tuple composed by a list of resource_download_param and the id of
            the boot resource used.
        """
        boot_resource = await self.boot_resources_service.create_or_update_from_simplestreams_product(
            product
        )

        (
            boot_resource_set,
            _,
        ) = await self.boot_resource_sets_service.get_or_create_from_simplestreams_product(
            product, boot_resource.id
        )

        resources_to_download: list[ResourceDownloadParam] = []

        # TODO: user-specified version (product.get_version_by_name())
        version = product.get_latest_version()

        for file in version.get_downloadable_files():
            # A ROOT_IMAGE may already be downloaded for the release if the stream
            # switched from one not containg SquashFS images to one that does. We
            # want to use the SquashFS image so delete the tgz.
            if file.ftype == BootResourceFileType.SQUASHFS_IMAGE:
                # delete the root image
                deleted_root_images = await self.boot_resource_files_service.delete_many(
                    query=QuerySpec(
                        where=BootResourceFileClauseFactory.and_clauses(
                            [
                                BootResourceFileClauseFactory.with_resource_set_id(
                                    boot_resource_set.id
                                ),
                                BootResourceFileClauseFactory.with_filetype(
                                    BootResourceFileType.ROOT_IMAGE
                                ),
                            ]
                        )
                    )
                )
                if deleted_root_images:
                    logger.debug(
                        "Deleted a root image tarball in favour of a root squashfs."
                    )

            resource_file = await self.boot_resource_files_service.get_or_create_from_simplestreams_file(
                file, boot_resource_set.id
            )

            local_file = resource_file.get_local_file()

            if (
                local_file.complete
                and await self.boot_resource_file_sync_service.file_sync_complete(
                    resource_file.id
                )
            ):
                logger.debug(
                    f"File with sha256 '{local_file.sha256}' already downloaded."
                )
                continue

            # Provide the extract path for bootloaders
            if (
                resource_file.filetype == BootResourceFileType.ARCHIVE_TAR_XZ
                and boot_resource.bootloader_type
            ):
                arch = boot_resource.architecture.split("/")[0]
                extract_path = (
                    f"{BOOTLOADERS_DIR}/{boot_resource.bootloader_type}/{arch}"
                )
            else:
                extract_path = None

            # Inside a Version, we can't have the same sha256
            resources_to_download.append(
                ResourceDownloadParam(
                    rfile_ids=[resource_file.id],
                    source_list=[f"{boot_source_url}/{file.path}"],
                    sha256=resource_file.sha256,
                    filename_on_disk=resource_file.filename_on_disk,
                    total_size=resource_file.size,
                    # force=force_download, # force isn't used anywhere
                    extract_paths=[extract_path] if extract_path else [],
                )
            )

        return (
            resources_to_download,
            boot_resource.id,
        )

    async def _boot_resource_is_duplicated(
        self,
        boot_resource: BootResource,
        boot_resources_to_delete_ids: set[int],
    ) -> bool:
        """Check if simplestreams provided another image with the same os, arch,
        series combination.

        Args:
            - boot_resource: the boot resource to check for duplicates
            - boot_resources_to_delete_ids: ids of the boot resources that are
            scheduled for removal. These are filtered out and not taken into account.

        NOTE: boot_resource name is composed by {os}/{series} while boot_resource
        architecture is in the form {arch}/{subarch}. When checking for duplicates,
        the sub-architecture is not taken into account.

        """
        return await self.boot_resources_service.exists(
            query=QuerySpec(
                where=BootResourceClauseFactory.and_clauses(
                    [
                        BootResourceClauseFactory.not_clause(
                            BootResourceClauseFactory.with_ids(
                                boot_resources_to_delete_ids
                            )
                        ),
                        BootResourceClauseFactory.with_name(
                            boot_resource.name
                        ),
                        BootResourceClauseFactory.with_architecture_starting_with(
                            boot_resource.architecture.split("/", maxsplit=1)[
                                0
                            ]
                        ),
                    ]
                )
            )
        )

    async def _boot_resource_is_selected(
        self,
        boot_resource: BootResource,
        resource_set_label: str,
        selections: list[BootSourceSelection],
    ) -> bool:
        """Returns True if the boot_resource matches one of the selections.

        Args:
            - boot_resource: the boot resource to check
            - resource_set_label: the label of the boot resource's set
            - selections: the selections to match
        """
        os, release = boot_resource.name.split("/")
        arch, subarch = boot_resource.architecture.split("/", 1)
        for selection in selections:
            arches = selection.arches or []
            subarches = selection.subarches or []
            labels = selection.labels or []
            if (
                os == selection.os
                and release == selection.release
                and (arch in arches or arches == ["*"])
                and (subarch in subarches or subarches == ["*"])
                and (resource_set_label in labels or labels == ["*"])
            ):
                return True
        return False

    async def delete_old_boot_resources(
        self, boot_resource_ids_to_keep: set[int]
    ) -> None:
        """Deletes the no more necessary boot resources.

        Deletes all the boot resources which:
            - don't have a boot resource set
            - don't relate to any boot source selection
            - are a duplicate of another boot resource

        It will keep the boot resources that are part of a selection even if
        they aren't present anymore in the simplestreams mirror. In such case,
        it will produce an event.

        Args:
            - boot_resource_ids_to_keep: a set of ids of boot resources that
              must not be deleted. This is coming from `get_files_to_download_from_product_list`
        """
        boot_resources_to_delete = await self.boot_resources_service.get_many(
            query=QuerySpec(
                where=BootResourceClauseFactory.and_clauses(
                    [
                        BootResourceClauseFactory.not_clause(
                            BootResourceClauseFactory.with_ids(
                                boot_resource_ids_to_keep
                            )
                        ),
                        BootResourceClauseFactory.with_rtype(
                            BootResourceType.SYNCED
                        ),
                    ]
                )
            )
        )
        if not boot_resources_to_delete:
            return

        boot_resources_to_delete_ids = {
            br.id for br in boot_resources_to_delete
        }
        selections = await self.boot_source_selections_service.get_many(
            query=QuerySpec()
        )
        for boot_resource in boot_resources_to_delete:
            boot_resource_set = await self.boot_resource_sets_service.get_latest_for_boot_resource(
                boot_resource.id
            )
            if (
                boot_resource_set
                and self._boot_resource_is_selected(
                    boot_resource, boot_resource_set.label, selections
                )
                and not self._boot_resource_is_duplicated(
                    boot_resource, boot_resources_to_delete_ids
                )
            ):
                # we keep the image because it's part of a selection but is not
                # present in simplestreams anymore
                await self.events_service.record_event(
                    event_type=EventTypeEnum.REGION_IMPORT_WARNING,
                    event_description=f"Boot image {boot_resource.name}/"
                    f"{boot_resource.architecture} no longer exists in stream, "
                    "but remains in selections. To delete this image remove its selection.",
                )
                boot_resources_to_delete_ids.remove(boot_resource.id)

        await self.boot_resources_service.delete_many(
            query=QuerySpec(
                where=BootResourceClauseFactory.with_ids(
                    boot_resources_to_delete_ids
                )
            )
        )

    async def delete_old_boot_resource_sets(self) -> None:
        """Deletes the old boot resource sets.

        For each boot resource, the most recent complete resource set is found,
        then all the others are deleted.

        """
        boot_resources = await self.boot_resources_service.get_many(
            query=QuerySpec(
                where=BootResourceClauseFactory.with_rtype(
                    BootResourceType.SYNCED
                )
            )
        )
        boot_resource_sets_to_delete = set()
        for boot_resource in boot_resources:
            found_first_complete_set = False
            resource_sets = await self.boot_resource_sets_service.get_many(
                query=QuerySpec(
                    where=BootResourceSetClauseFactory.with_resource_id(
                        boot_resource.id
                    ),
                    order_by=[
                        OrderByClauseFactory.desc_clause(
                            BootResourceSetsOrderByClauses.by_id()
                        )
                    ],
                )
            )
            for resource_set in resource_sets:
                if not await self.boot_resource_file_sync_service.resource_set_sync_complete(
                    resource_set.id
                ):
                    boot_resource_sets_to_delete.add(resource_set.id)
                else:
                    if not found_first_complete_set:
                        # we keep the first complete set and delete the others
                        found_first_complete_set = True
                    else:
                        boot_resource_sets_to_delete.add(resource_set.id)

        await self.boot_resource_sets_service.delete_many(
            query=QuerySpec(
                where=BootResourceFileClauseFactory.with_resource_set_ids(
                    list(boot_resource_sets_to_delete)
                )
            )
        )

        await self.boot_resources_service.delete_all_without_sets()
