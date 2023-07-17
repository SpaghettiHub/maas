# Copyright 2018 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import os
from pathlib import Path
from unittest.mock import Mock

from fixtures import EnvironmentVariable
from twisted.internet.defer import inlineCallbacks

from maasserver.listener import notify
from maasserver.models import Config
from maasserver.regiondservices import certificate_expiration_check, http
from maasserver.secrets import SecretManager
from maasserver.testing.testcase import MAASTransactionServerTestCase
from maasserver.triggers.testing import TransactionalHelpersMixin
from maasserver.utils.threads import deferToDatabase
from maasserver.workers import WorkersService
from maastesting.crochet import wait_for
from provisioningserver.testing.certificates import (
    get_sample_cert_with_cacerts,
)

wait_for_reactor = wait_for()


class TestRegionHTTPService(
    TransactionalHelpersMixin, MAASTransactionServerTestCase
):
    def setUp(self):
        super().setUp()
        self.cert = get_sample_cert_with_cacerts()

    def create_tls_config(self):
        def _create_config_in_db():
            Config.objects.set_config("tls_port", 5443)
            SecretManager().set_composite_secret(
                "tls",
                {
                    "key": self.cert.private_key_pem(),
                    "cert": self.cert.certificate_pem(),
                    "cacert": self.cert.ca_certificates_pem(),
                },
            )
            # manually send a notification to emulate what TLS config does
            notify("sys_reverse_proxy")

        yield deferToDatabase(_create_config_in_db)

    @wait_for_reactor
    @inlineCallbacks
    def test_configure_and_reload_not_snap(self):
        service = http.RegionHTTPService()
        mock_reloadService = self.patch(http.service_monitor, "reloadService")
        mock_configure = self.patch(service, "_configure")
        mock_cert_check = self.patch(
            certificate_expiration_check, "check_tls_certificate"
        )

        yield from self.create_tls_config()
        yield service.startService()
        yield service.stopService()
        mock_configure.assert_called_once()
        mock_reloadService.assert_called_once_with("reverse_proxy")
        mock_cert_check.assert_called_once_with()

    @wait_for_reactor
    @inlineCallbacks
    def test_configure_and_reload_in_snap(self):
        self.useFixture(EnvironmentVariable("SNAP", "/snap/maas/current"))
        service = http.RegionHTTPService()
        mock_restartService = self.patch(
            http.service_monitor, "restartService"
        )
        mock_configure = self.patch(service, "_configure")
        mock_cert_check = self.patch(
            certificate_expiration_check, "check_tls_certificate"
        )

        yield from self.create_tls_config()
        yield service.startService()

        yield service.stopService()
        mock_configure.assert_called_once()
        mock_restartService.assert_called_once_with("reverse_proxy")
        mock_cert_check.assert_called_once_with()

    def test_configure_not_snap(self):
        # MAASDataFixture updates `MAAS_DATA` in the environment to point to this new location.
        data_path = os.getenv("MAAS_DATA")
        http.REGIOND_SOCKET_PATH = f"{data_path}/maas-regiond-webapp.sock"

        tempdir = self.make_dir()
        nginx_conf = Path(tempdir) / "regiond.nginx.conf"
        service = http.RegionHTTPService()
        self.patch(http, "compose_http_config_path").return_value = str(
            nginx_conf
        )

        mock_create_cert_files = self.patch(service, "_create_cert_files")
        mock_create_cert_files.return_value = ("key_path", "cert_path")

        service._configure(http._Configuration(self.cert, port=5443))

        nginx_config = nginx_conf.read_text()

        worker_ids = WorkersService.get_worker_ids()
        for worker_id in worker_ids:
            self.assertIn(
                f"{data_path}/maas-regiond-webapp.sock.{worker_id};",
                nginx_config,
            )
        self.assertIn("root /usr/share/maas/web/static;", nginx_config)
        self.assertIn("listen 5443 ssl http2;", nginx_config)
        self.assertIn("ssl_certificate cert_path;", nginx_config)
        self.assertIn("ssl_certificate_key key_path;", nginx_config)

    def test_configure_in_snap(self):
        self.patch(
            os,
            "environ",
            {
                "SNAP": "/snap/maas/5443",
                "MAAS_HTTP_CONFIG_DIR": os.getenv("MAAS_DATA"),
            },
        )
        http.REGIOND_SOCKET_PATH = "/snap/maas/maas-regiond-webapp.sock"

        tempdir = self.make_dir()
        nginx_conf = Path(tempdir) / "regiond.nginx.conf"
        service = http.RegionHTTPService()
        self.patch(http, "compose_http_config_path").return_value = str(
            nginx_conf
        )

        mock_create_cert_files = self.patch(service, "_create_cert_files")
        mock_create_cert_files.return_value = ("key_path", "cert_path")

        service._configure(http._Configuration(cert=self.cert, port=5443))

        nginx_config = nginx_conf.read_text()
        worker_ids = WorkersService.get_worker_ids()
        for worker_id in worker_ids:
            self.assertIn(
                f"server unix:/snap/maas/maas-regiond-webapp.sock.{worker_id};",
                nginx_config,
            )
        self.assertIn(
            "root /snap/maas/5443/usr/share/maas/web/static;", nginx_config
        )
        self.assertIn("listen 5443 ssl http2;", nginx_config)
        self.assertIn("ssl_certificate cert_path;", nginx_config)
        self.assertIn("ssl_certificate_key key_path;", nginx_config)

    def test_configure_https_also_has_http_server(self):
        tempdir = self.make_dir()
        nginx_conf = Path(tempdir) / "regiond.nginx.conf"
        service = http.RegionHTTPService()
        self.patch(http, "compose_http_config_path").return_value = str(
            nginx_conf
        )

        mock_create_cert_files = self.patch(service, "_create_cert_files")
        mock_create_cert_files.return_value = ("key_path", "cert_path")

        service._configure(http._Configuration(cert=self.cert, port=5443))

        nginx_config = nginx_conf.read_text()
        self.assertIn("listen 5443 ssl http2;", nginx_config)
        self.assertIn("listen 5240;", nginx_config)
        self.assertIn("location /MAAS/api/2.0/machines {", nginx_config)

    def test_create_cert_files_writes_full_chain(self):
        tempdir = Path(self.make_dir())
        certs_dir = tempdir / "certs"
        certs_dir.mkdir()
        self.patch(http, "get_http_config_dir").return_value = tempdir

        service = http.RegionHTTPService()
        service._create_cert_files(self.cert)
        self.assertEqual(
            (certs_dir / "regiond-proxy.pem").read_text(),
            self.cert.fullchain_pem(),
        )
        self.assertEqual(
            (certs_dir / "regiond-proxy-key.pem").read_text(),
            self.cert.private_key_pem(),
        )

    @wait_for_reactor
    @inlineCallbacks
    def test_registers_and_unregisters_listener(self):
        listener = Mock()
        service = http.RegionHTTPService(postgresListener=listener)
        self.patch(http.service_monitor, "reloadService")
        self.patch(service, "_configure")

        yield service.startService()
        listener.register.assert_called_once_with(
            "sys_reverse_proxy", service._consume_event
        )

        yield service.stopService()
        listener.unregister.assert_called_once_with(
            "sys_reverse_proxy", service._consume_event
        )

    @wait_for_reactor
    @inlineCallbacks
    def test_handler_is_called_on_config_change(self):
        listener = self.make_listener_without_delay()
        capture = []

        def _handler(channel, payload):
            capture.append(channel)

        listener.register("sys_reverse_proxy", _handler)
        self.addCleanup(listener.unregister, "sys_reverse_proxy", _handler)
        yield listener.startService()
        yield from self.create_tls_config()
        try:
            self.assertEqual(capture, ["sys_reverse_proxy"])
        finally:
            yield listener.stopService()

    @wait_for_reactor
    @inlineCallbacks
    def test_data_is_consistent_when_notified(self):
        listener = self.make_listener_without_delay()
        capture = []

        def _handler(channel, payload):
            capture.append(channel)

        listener.register("sys_reverse_proxy", _handler)
        self.addCleanup(listener.unregister, "sys_reverse_proxy", _handler)
        yield listener.startService()
        yield from self.create_tls_config()
        try:
            self.assertEqual(capture, ["sys_reverse_proxy"])
        finally:
            yield listener.stopService()

        def get_config():
            tls_port = Config.objects.get_config("tls_port")
            tls_secrets = SecretManager().get_composite_secret("tls")
            return tls_port, tls_secrets

        tls_port, tls_secrets = yield deferToDatabase(get_config)
        self.assertEqual(tls_port, 5443)
        self.assertEqual(
            tls_secrets,
            {
                "key": self.cert.private_key_pem(),
                "cert": self.cert.certificate_pem(),
                "cacert": self.cert.ca_certificates_pem(),
            },
        )
