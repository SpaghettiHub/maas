# Copyright 2025 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

from unittest.mock import ANY, MagicMock, patch

import pytest

from maasservicelayer.context import Context
from maasservicelayer.services.boot_sources import BootSourcesService
from maastesting.factory import factory


@pytest.mark.asyncio
class TestBootSourcesService:
    @patch("maasservicelayer.services.boot_sources.RepoDumper.sync")
    @patch("maasservicelayer.services.boot_sources.UrlMirrorReader")
    async def test_fetch(
        self,
        urlmirrorreader_mock: MagicMock,
        repodumper_sync_mock: MagicMock,
    ) -> None:
        boot_sources_service = BootSourcesService(context=Context())

        source_url = factory.make_url()
        expected_mirror_url = "streams/v1/index.sjson"

        boot_sources_service._fetch(source_url)

        # Also doesn't pass user agent when not set.
        repodumper_sync_mock.assert_called_once_with(
            urlmirrorreader_mock.return_value,
            expected_mirror_url,
        )
        urlmirrorreader_mock.assert_called_once_with(
            source_url,
            policy=ANY,
            user_agent=None,
        )

    @patch("maasservicelayer.services.boot_sources.RepoDumper.sync")
    @patch("maasservicelayer.services.boot_sources.UrlMirrorReader")
    async def test_fetch_with_user_agent(
        self,
        urlmirrorreader_mock: MagicMock,
        repodumper_sync_mock: MagicMock,
    ) -> None:
        boot_sources_service = BootSourcesService(context=Context())

        source_url = factory.make_url()
        user_agent = factory.make_name("user-agent")
        expected_mirror_url = "streams/v1/index.sjson"

        boot_sources_service._fetch(source_url, user_agent=user_agent)

        repodumper_sync_mock.assert_called_once_with(
            urlmirrorreader_mock.return_value,
            expected_mirror_url,
        )
        urlmirrorreader_mock.assert_called_once_with(
            source_url,
            policy=ANY,
            user_agent=user_agent,
        )
