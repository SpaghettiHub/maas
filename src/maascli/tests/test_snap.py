# Copyright 2017 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import io
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
from textwrap import dedent
import time
from unittest.mock import MagicMock

from fixtures import EnvironmentVariableFixture
import netifaces
import pytest

from maascli import snap
from maascli.command import CommandError
from maascli.parser import ArgumentParser
from maastesting.factory import factory
from maastesting.testcase import MAASTestCase


class TestHelpers(MAASTestCase):
    def setUp(self):
        super().setUp()
        snap_common = self.make_dir()
        snap_data = self.make_dir()
        self.environ = {"SNAP_COMMON": snap_common, "SNAP_DATA": snap_data}
        self.patch(os, "environ", self.environ)

    def test_get_default_gateway_ip_no_defaults(self):
        self.patch(netifaces, "gateways").return_value = {}
        self.assertIsNone(snap.get_default_gateway_ip())

    def test_get_default_gateway_ip_returns_ipv4(self):
        gw_address = factory.make_ipv4_address()
        ipv4_address = factory.make_ipv4_address()
        iface_name = factory.make_name("eth")
        self.patch(netifaces, "gateways").return_value = {
            "default": {netifaces.AF_INET: (gw_address, iface_name)}
        }
        self.patch(netifaces, "ifaddresses").return_value = {
            netifaces.AF_INET: [{"addr": ipv4_address}]
        }
        self.assertEqual(ipv4_address, snap.get_default_gateway_ip())

    def test_get_default_gateway_ip_returns_ipv6(self):
        gw_address = factory.make_ipv6_address()
        ipv6_address = factory.make_ipv6_address()
        iface_name = factory.make_name("eth")
        self.patch(netifaces, "gateways").return_value = {
            "default": {netifaces.AF_INET6: (gw_address, iface_name)}
        }
        self.patch(netifaces, "ifaddresses").return_value = {
            netifaces.AF_INET6: [{"addr": ipv6_address}]
        }
        self.assertEqual(ipv6_address, snap.get_default_gateway_ip())

    def test_get_default_gateway_ip_returns_ipv4_over_ipv6(self):
        gw4_address = factory.make_ipv4_address()
        gw6_address = factory.make_ipv6_address()
        ipv4_address = factory.make_ipv4_address()
        ipv6_address = factory.make_ipv6_address()
        iface = factory.make_name("eth")
        self.patch(netifaces, "gateways").return_value = {
            "default": {
                netifaces.AF_INET: (gw4_address, iface),
                netifaces.AF_INET6: (gw6_address, iface),
            }
        }
        self.patch(netifaces, "ifaddresses").return_value = {
            netifaces.AF_INET: [{"addr": ipv4_address}],
            netifaces.AF_INET6: [{"addr": ipv6_address}],
        }
        self.assertEqual(ipv4_address, snap.get_default_gateway_ip())

    def test_get_default_gateway_ip_returns_first_ip(self):
        gw_address = factory.make_ipv4_address()
        ipv4_address1 = factory.make_ipv4_address()
        ipv4_address2 = factory.make_ipv4_address()
        iface = factory.make_name("eth")
        self.patch(netifaces, "gateways").return_value = {
            "default": {netifaces.AF_INET: (gw_address, iface)}
        }
        self.patch(netifaces, "ifaddresses").return_value = {
            netifaces.AF_INET: [
                {"addr": ipv4_address1},
                {"addr": ipv4_address2},
            ]
        }
        self.assertEqual(ipv4_address1, snap.get_default_gateway_ip())

    def test_get_default_url_uses_gateway_ip(self):
        ipv4_address = factory.make_ipv4_address()
        self.patch(snap, "get_default_gateway_ip").return_value = ipv4_address
        self.assertEqual(
            "http://%s:5240/MAAS" % ipv4_address, snap.get_default_url()
        )

    def test_get_default_url_fallsback_to_localhost(self):
        self.patch(snap, "get_default_gateway_ip").return_value = None
        self.assertEqual("http://localhost:5240/MAAS", snap.get_default_url())

    def test_get_mode_filepath(self):
        self.assertEqual(
            os.path.join(self.environ["SNAP_COMMON"], "snap_mode"),
            snap.get_mode_filepath(),
        )

    def test_get_current_mode_returns_none_when_missing(self):
        self.assertEqual("none", snap.get_current_mode())

    def test_get_current_mode_returns_file_contents(self):
        snap.set_current_mode("all")
        self.assertEqual("all", snap.get_current_mode())

    def test_set_current_mode_creates_file(self):
        snap.set_current_mode("all")
        self.assertTrue(os.path.exists(snap.get_mode_filepath()))

    def test_set_current_mode_overwrites(self):
        snap.set_current_mode("all")
        snap.set_current_mode("none")
        self.assertEqual("none", snap.get_current_mode())


class TestRenderSupervisord:

    TEST_TEMPLATE = dedent(
        """\
    {{if regiond}}
    HAS_REGIOND
    {{endif}}
    {{if rackd}}
    HAS_RACKD
    {{endif}}
    """
    )

    @pytest.mark.parametrize(
        "mode,has_regiond,has_rackd",
        [
            ("region+rack", True, True),
            ("region", True, False),
            ("rack", False, True),
            ("none", False, False),
        ],
    )
    def test_template_rendered_correctly(
        self,
        mocker,
        monkeypatch,
        tmp_path_factory,
        mode,
        has_regiond,
        has_rackd,
    ):
        snap_dir = tmp_path_factory.mktemp("snap")
        maas_share = snap_dir / "usr" / "share" / "maas"
        maas_share.mkdir(parents=True)
        (maas_share / "supervisord.conf.template").write_text(
            self.TEST_TEMPLATE
        )
        snap_data = tmp_path_factory.mktemp("snap_data")
        (snap_data / "supervisord").mkdir()
        monkeypatch.setenv("SNAP", str(snap_dir))
        monkeypatch.setenv("SNAP_DATA", str(snap_data))

        snap.render_supervisord(mode)
        output = (snap_data / "supervisord" / "supervisord.conf").read_text()
        assert ("HAS_REGIOND" in output) == has_regiond
        assert ("HAS_RACKD" in output) == has_rackd


class TestSupervisordHelpers(MAASTestCase):
    def test_get_supervisord_pid_returns_None(self):
        snap_data = self.make_dir()
        self.patch(os, "environ", {"SNAP_DATA": snap_data})
        self.assertIsNone(snap.get_supervisord_pid())

    def test_get_supervisord_pid_returns_pid(self):
        pid = random.randint(2, 99)
        snap_data = self.make_dir()
        supervisord_dir = os.path.join(snap_data, "supervisord")
        os.makedirs(supervisord_dir)
        with open(
            os.path.join(supervisord_dir, "supervisord.pid"), "w"
        ) as stream:
            stream.write("%s" % pid)
        self.patch(os, "environ", {"SNAP_DATA": snap_data})
        self.assertEqual(pid, snap.get_supervisord_pid())

    def test_sighup_supervisord_sends_SIGHUP(self):
        pid = random.randint(2, 99)
        snap_dir = self.make_dir()
        self.patch(os, "environ", {"SNAP": snap_dir})
        self.patch(snap, "get_supervisord_pid").return_value = pid
        mock_kill = self.patch(os, "kill")
        self.patch(time, "sleep")  # Speed up the test.
        mock_process = MagicMock()
        mock_popen = self.patch(subprocess, "Popen")
        mock_popen.return_value = mock_process
        snap.sighup_supervisord()
        mock_kill.assert_called_once_with(pid, signal.SIGHUP)
        mock_popen.assert_called_once_with(
            [os.path.join(snap_dir, "bin", "run-supervisorctl"), "status"],
            stdout=subprocess.PIPE,
        )
        mock_process.wait.assert_called_once_with()

    def test_sighup_supervisord_nop_if_not_running(self):
        pid = random.randint(2, 99)
        snap_dir = self.make_dir()
        self.patch(os, "environ", {"SNAP": snap_dir})
        self.patch(snap, "get_supervisord_pid").return_value = pid
        mock_kill = self.patch(os, "kill")
        mock_kill.side_effect = ProcessLookupError()
        # the command doesn't fail
        snap.sighup_supervisord()
        mock_kill.assert_called_once_with(pid, signal.SIGHUP)

    def test_sighup_supervisord_waits_until_no_error(self):
        pid = random.randint(2, 99)
        snap_dir = self.make_dir()
        self.patch(os, "environ", {"SNAP": snap_dir})
        self.patch(snap, "get_supervisord_pid").return_value = pid
        mock_kill = self.patch(os, "kill")
        self.patch(time, "sleep")  # Speed up the test.
        mock_process = MagicMock()
        mock_process.stdout.read.side_effect = [b"error:", b""]
        mock_popen = self.patch(subprocess, "Popen")
        mock_popen.return_value = mock_process
        snap.sighup_supervisord()
        mock_kill.assert_called_once_with(pid, signal.SIGHUP)
        self.assertEqual(2, mock_popen.call_count)


class TestConfigHelpers(MAASTestCase):
    def setUp(self):
        super().setUp()
        maas_data = self.make_dir()
        self.secret_file = Path(maas_data) / "secret"
        self.useFixture(EnvironmentVariableFixture("MAAS_DATA", maas_data))

    def test_print_config_value(self):
        mock_print = self.patch(snap, "print_msg")
        key = factory.make_name("key")
        value = factory.make_name("value")
        config = {key: value}
        snap.print_config_value(config, key)
        mock_print.assert_called_once_with("{}={}".format(key, value))

    def test_print_config_value_hidden(self):
        mock_print = self.patch(snap, "print_msg")
        key = factory.make_name("key")
        value = factory.make_name("value")
        config = {key: value}
        snap.print_config_value(config, key, hidden=True)
        mock_print.assert_called_once_with("{}=(hidden)".format(key))

    def test_get_rpc_secret_returns_secret(self):
        secret = factory.make_string()
        self.secret_file.write_text(secret)
        self.assertEqual(snap.get_rpc_secret(), secret)

    def test_get_rpc_secret_returns_None_when_no_file(self):
        self.assertIsNone(snap.get_rpc_secret())

    def test_get_rpc_secret_returns_None_when_empty_file(self):
        self.secret_file.write_text("")
        self.assertIsNone(snap.get_rpc_secret())

    def test_set_rpc_secret_sets_secret(self):
        secret = factory.make_string()
        snap.set_rpc_secret(secret)
        self.assertEqual(secret, snap.get_rpc_secret())

    def test_set_rpc_secret_clears_secret(self):
        secret = factory.make_string()
        snap.set_rpc_secret(secret)
        snap.set_rpc_secret(None)
        self.assertIsNone(snap.get_rpc_secret())
        self.assertFalse(self.secret_file.exists())


class TestCmdInit(MAASTestCase):
    def setUp(self):
        super().setUp()
        self.parser = ArgumentParser()
        self.cmd = snap.cmd_init(self.parser)
        self.patch(os, "getuid").return_value = 0
        self.snap_common = self.make_dir()
        self.patch(
            os,
            "environ",
            {
                "SNAP": "/snap/maas",
                "SNAP_COMMON": self.snap_common,
                "SNAP_DATA": "/snap/maas/data",
            },
        )
        self.mock_read_input = self.patch(snap, "read_input")

    def test_init_snap_db_options_prompt(self):
        self.mock_maas_configuration = self.patch(snap, "MAASConfiguration")
        self.patch(snap, "set_rpc_secret")
        self.patch(snap.cmd_init, "_finalize_init")

        self.mock_read_input.side_effect = [
            "postgres://maas:pwd@localhost/db",
            "http://localhost:5240/MAAS",
        ]
        options = self.parser.parse_args(["region+rack"])
        self.cmd(options)
        self.mock_maas_configuration().update.assert_called_once_with(
            {
                "maas_url": "http://localhost:5240/MAAS",
                "database_host": "localhost",
                "database_name": "db",
                "database_user": "maas",
                "database_pass": "pwd",
            }
        )

    def test_init_db_parse_error(self):
        self.patch(snap, "print_msg")
        self.mock_maas_configuration = self.patch(snap, "MAASConfiguration")
        self.patch(snap, "set_rpc_secret")
        self.patch(snap.cmd_init, "_finalize_init")

        self.mock_read_input.side_effect = [
            "localhost",
            "db",
            "maas",
            "pwd",
            "http://localhost:5240/MAAS",
        ]
        options = self.parser.parse_args(
            ["region+rack", "--database-uri", "invalid"]
        )
        error = self.assertRaises(CommandError, self.cmd, options)
        self.assertEqual(
            "Database URI needs to be either 'maas-test-db:///' or start "
            "with 'postgres://'",
            str(error),
        )
        self.mock_maas_configuration().update.assert_not_called()

    def test_get_database_settings_no_prompt_dsn(self):
        options = self.parser.parse_args(
            [
                "region+rack",
                "--database-uri",
                "postgres://dbuser:pwd@dbhost/dbname",
            ]
        )
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": "dbhost",
                "database_name": "dbname",
                "database_user": "dbuser",
                "database_pass": "pwd",
            },
            settings,
        )

    def test_get_database_settings_prompt_dsn(self):
        self.mock_read_input.side_effect = [
            "postgres://dbuser:pwd@dbhost/dbname"
        ]
        options = self.parser.parse_args(["region+rack"])
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": "dbhost",
                "database_name": "dbname",
                "database_user": "dbuser",
                "database_pass": "pwd",
            },
            settings,
        )

    def test_get_database_settings_maas_test_db_prompt_default(self):
        options = self.parser.parse_args(["region+rack"])
        os.mkdir(os.path.join(self.snap_common, "test-db-socket"))
        self.mock_read_input.side_effect = [""]
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": f"{self.snap_common}/test-db-socket",
                "database_name": "maasdb",
                "database_user": "maas",
                "database_pass": None,
            },
            settings,
        )

    def test_get_database_settings_maas_test_db_prompt_no_default(self):
        options = self.parser.parse_args(["region+rack"])
        self.mock_read_input.side_effect = ["", "postgres:///?user=foo"]
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": "localhost",
                "database_name": "foo",
                "database_user": "foo",
                "database_pass": None,
            },
            settings,
        )

    def test_get_database_settings_maas_test_db(self):
        options = self.parser.parse_args(
            ["region+rack", "--database-uri", "maas-test-db:///"]
        )
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": f"{self.snap_common}/test-db-socket",
                "database_name": "maasdb",
                "database_user": "maas",
                "database_pass": None,
            },
            settings,
        )

    def test_get_database_settings_minimal_postgres(self):
        options = self.parser.parse_args(
            ["region+rack", "--database-uri", "postgres:///?user=myuser"]
        )
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": "localhost",
                "database_name": "myuser",
                "database_user": "myuser",
                "database_pass": None,
            },
            settings,
        )

    def test_get_database_settings_full_postgres(self):
        options = self.parser.parse_args(
            [
                "region+rack",
                "--database-uri",
                "postgres://myuser:pwd@myhost:1234/mydb",
            ]
        )
        settings = snap.get_database_settings(options)
        self.assertEqual(
            {
                "database_host": "myhost",
                "database_name": "mydb",
                "database_user": "myuser",
                "database_pass": "pwd",
                "database_port": 1234,
            },
            settings,
        )

    def test_get_database_settings_invalid_parameters(self):
        options = self.parser.parse_args(
            [
                "region+rack",
                "--database-uri",
                "postgres://myuser:pwd@myhost:1234/mydb?foo=bar",
            ]
        )
        error = self.assertRaises(
            snap.DatabaseSettingsError, snap.get_database_settings, options
        )
        self.assertEqual(
            "Error parsing database URI: "
            'invalid dsn: invalid URI query parameter: "foo"',
            str(error),
        )

    def test_get_database_settings_unsupported_parameters(self):
        options = self.parser.parse_args(
            [
                "region+rack",
                "--database-uri",
                "postgres://myuser:pwd@myhost/?passfile=foo&options=bar",
            ]
        )
        error = self.assertRaises(
            snap.DatabaseSettingsError, snap.get_database_settings, options
        )
        self.assertEqual(
            "Error parsing database URI: "
            "Unsupported parameters: options, passfile",
            str(error),
        )

    def test_get_database_settings_missing_user(self):
        options = self.parser.parse_args(
            ["region+rack", "--database-uri", "postgres://myhost/"]
        )
        error = self.assertRaises(
            snap.DatabaseSettingsError, snap.get_database_settings, options
        )
        self.assertEqual(
            "No user found in URI: postgres://myhost/", str(error)
        )

    def test_get_database_settings_invalid_maas_test_db(self):
        options = self.parser.parse_args(
            ["region+rack", "--database-uri", "maas-test-db:///foo"]
        )
        error = self.assertRaises(
            snap.DatabaseSettingsError, snap.get_database_settings, options
        )
        self.assertEqual(
            "Database URI needs to be either 'maas-test-db:///' or start with "
            "'postgres://'",
            str(error),
        )

    def test_get_database_settings_incomplete_postgres_uri(self):
        # The URI needs to start with at least postgres:// before we
        # even try to parse it.
        options = self.parser.parse_args(
            ["region+rack", "--database-uri", "postgres:/"]
        )
        error = self.assertRaises(
            snap.DatabaseSettingsError, snap.get_database_settings, options
        )
        self.assertEqual(
            "Database URI needs to be either 'maas-test-db:///' or start with "
            "'postgres://'",
            str(error),
        )


class TestCmdStatus(MAASTestCase):
    def test_requires_root(self):
        parser = ArgumentParser()
        cmd = snap.cmd_status(parser)
        self.patch(os, "getuid").return_value = 1000
        error = self.assertRaises(SystemExit, cmd, parser.parse_args([]))
        self.assertEqual(
            str(error), "The 'status' command must be run by root."
        )


class TestCmdConfig(MAASTestCase):
    def setUp(self):
        super().setUp()
        self.parser = ArgumentParser()
        self.cmd = snap.cmd_config(self.parser)
        self.patch(os, "getuid").return_value = 0
        snap_common = self.make_dir()
        snap_data = self.make_dir()
        self.useFixture(EnvironmentVariableFixture("SNAP_COMMON", snap_common))
        self.useFixture(EnvironmentVariableFixture("SNAP_DATA", snap_data))

    def test_show(self):
        # Regression test for LP:1892868
        stdout = io.StringIO()
        self.patch(sys, "stdout", stdout)
        options = self.parser.parse_args([])
        self.assertIsNone(self.cmd(options))
        self.assertEqual(stdout.getvalue(), "Mode: none\n")

    def test_enable_debugging(self):
        mock_maas_configuration = self.patch(snap, "MAASConfiguration")
        mock_sighup_supervisord = self.patch(snap, "sighup_supervisord")
        options = self.parser.parse_args(["--enable-debug"])
        stdout = io.StringIO()
        self.patch(sys, "stdout", stdout)

        self.cmd(options)
        mock_maas_configuration().update.assert_called_once_with(
            {"debug": True}
        )
        # After config is changed, services are restarted
        self.assertEqual(stdout.getvalue(), "Stopping services\n")
        mock_sighup_supervisord.assert_called_once_with()

    def test_reenable_debugging(self):
        mock_maas_configuration = self.patch(snap, "MAASConfiguration")
        config_manager = mock_maas_configuration()
        mock_sighup_supervisord = self.patch(snap, "sighup_supervisord")
        options = self.parser.parse_args(["--enable-debug"])
        stdout = io.StringIO()
        self.patch(sys, "stdout", stdout)

        # Simulate the value already being enabled
        current_config = config_manager.get()
        current_config.get.side_effect = {"debug": True}.__getitem__

        self.cmd(options)
        config_manager.update.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        mock_sighup_supervisord.assert_not_called()


class TestDBNeedInit(MAASTestCase):
    def test_has_tables(self):
        connection = MagicMock()
        connection.introspection.table_names.return_value = [
            "table1",
            "table2",
        ]
        self.assertFalse(snap.db_need_init(connection))

    def test_no_tables(self):
        connection = MagicMock()
        connection.introspection.table_names.return_value = []
        self.assertTrue(snap.db_need_init(connection))

    def test_fail(self):
        connection = MagicMock()
        connection.introspection.table_names.side_effect = Exception(
            "connection failed"
        )
        self.assertTrue(snap.db_need_init(connection))
