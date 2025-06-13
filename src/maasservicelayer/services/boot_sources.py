#  Copyright 2025 Canonical Ltd.  This software is licensed under the
#  GNU Affero General Public License version 3 (see the file LICENSE).

import asyncio

from simplestreams.mirrors import UrlMirrorReader
from simplestreams.util import path_from_mirror_url
import structlog

from maasservicelayer.context import Context
from maasservicelayer.services.base import Service
from maasservicelayer.utils.images.boot_image_mapping import BootImageMapping
from maasservicelayer.utils.images.helpers import get_signing_policy
from maasservicelayer.utils.images.repo_dumper import RepoDumper

logger = structlog.getLogger()


class BootSourcesService(Service):
    def __init__(self, context: Context) -> None:
        super().__init__(context)

    async def fetch(
        self,
        source_url: str,
        keyring: str | None = None,
        user_agent: str | None = None,
        validate_products: bool = True,
    ) -> BootImageMapping:
        """Download image metadata from upstream Simplestreams repo.

        :param path: The path to a Simplestreams repo.
        :param keyring: Optional keyring for verifying the repo's signatures.
        :param user_agent: Optional user agent string for downloading the image
            descriptions.
        :return: A `BootImageMapping` describing available boot resources.
        """
        return await asyncio.to_thread(
            self._fetch,
            source_url,
            keyring,
            user_agent,
            validate_products,
        )

    def _fetch(
        self,
        source_url: str,
        keyring: str | None = None,
        user_agent: str | None = None,
        validate_products: bool = True,
    ) -> BootImageMapping:
        logger.info(f"Downloading image descriptions from '{source_url}'.")
        mirror, rpath = path_from_mirror_url(source_url, None)
        policy = get_signing_policy(rpath, keyring)

        # Since user_agent is set, we know we are downloading descriptions
        # from the Images repository *by* the Region.
        logger.info(
            f"Region downloading image descriptions from '{source_url}'."
        )
        reader = UrlMirrorReader(mirror, policy=policy, user_agent=user_agent)

        boot_images_dict = BootImageMapping()
        dumper = RepoDumper(
            boot_images_dict, validate_products=validate_products
        )
        dumper.sync(reader, rpath)
        return boot_images_dict
