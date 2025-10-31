# Copyright 2016 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for process helpers."""

import os
import random
from textwrap import dedent
from unittest.mock import Mock

from maastesting.factory import factory
from maastesting.testcase import MAASTestCase
from provisioningserver.utils import ps as ps_module
from provisioningserver.utils.fs import atomic_write
from provisioningserver.utils.ps import (
    get_running_pids_with_command,
    is_pid_in_container,
    is_pid_running,
    running_in_container,
)
from provisioningserver.utils.shell import ExternalProcessError

NOT_IN_CONTAINER = dedent(
    """\
    11:freezer:/
    10:perf_event:/
    9:cpuset:/
    8:net_cls,net_prio:/init.scope
    7:devices:/init.scope
    6:blkio:/init.scope
    5:memory:/init.scope
    4:cpu,cpuacct:/init.scope
    3:pids:/init.scope
    2:hugetlb:/
    1:name=systemd:/init.scope
    """
)

IN_DOCKER_CONTAINER = dedent(
    """\
    11:freezer:/system.slice/docker-8467.scope
    10:perf_event:/
    9:cpuset:/system.slice/docker-8467.scope
    8:net_cls,net_prio:/init.scope
    7:devices:/init.scope/system.slice/docker-8467.scope
    6:blkio:/system.slice/docker-8467.scope
    5:memory:/system.slice/docker-8467.scope
    4:cpu,cpuacct:/system.slice/docker-8467.scope
    3:pids:/system.slice/docker-8467.scopeatomic_write
    2:hugetlb:/
    1:name=systemd:/system.slice/docker-8467.scope
    """
)

IN_LXC_CONTAINER = dedent(
    """\
    11:hugetlb:/lxc/maas
    10:perf_event:/lxc/maas
    9:blkio:/lxc/maas
    8:freezer:/lxc/maas
    7:devices:/lxc/maas/init.scope
    6:memory:/lxc/maas
    5:cpuacct:/lxc/maas
    4:cpu:/lxc/maas
    3:name=systemd:/lxc/maas/init.scope
    2:cpuset:/lxc/maas
    """
)


class TestIsPIDRunning(MAASTestCase):
    scenarios = (
        ("running", {"result": True, "exception": None}),
        ("lookup-error", {"result": False, "exception": ProcessLookupError()}),
        ("permission-error", {"result": True, "exception": PermissionError()}),
        ("os-error", {"result": False, "exception": OSError()}),
    )

    def test_result(self):
        self.patch(ps_module.os, "kill").side_effect = self.exception
        self.assertEqual(self.result, is_pid_running(random.randint(100, 200)))


class TestIsPIDInContainer(MAASTestCase):
    scenarios = (
        ("not_in_container", {"result": False, "cgroup": NOT_IN_CONTAINER}),
        (
            "in_docker_container",
            {"result": True, "cgroup": IN_DOCKER_CONTAINER},
        ),
        ("in_lxc_container", {"result": True, "cgroup": IN_LXC_CONTAINER}),
    )

    def test_result(self):
        proc_path = self.make_dir()
        pid = random.randint(1, 1000)
        pid_path = os.path.join(proc_path, str(pid))
        os.mkdir(pid_path)
        atomic_write(
            self.cgroup.encode("ascii"), os.path.join(pid_path, "cgroup")
        )
        self.assertEqual(
            self.result, is_pid_in_container(pid, proc_path=proc_path)
        )


class TestRunningInContainer(MAASTestCase):
    def test_returns_False_when_ExternalProcessError(self):
        mock_call = self.patch(ps_module, "call_and_check")
        mock_call.side_effect = ExternalProcessError(
            1, ["systemd-detect-virt", "-c"], output="none"
        )
        running_in_container.cache_clear()
        self.assertFalse(running_in_container())

    def test_returns_True_when_not_ExternalProcessError(self):
        self.patch(ps_module, "call_and_check")
        running_in_container.cache_clear()
        self.assertTrue(running_in_container())


class TestGetRunningPIDsWithCommand(MAASTestCase):
    def test_returns_processes_running_on_host_not_container(self):
        command = factory.make_name("command")

        ps_output = (
            "  PID COMMAND\n"
            "   1 init\n"
            "   malformedline\n"
            "   malformed line\n"
            "   10 othercmd\n"
            "   20 %s\n"
            "   30 %s\n"
            "   40 %s\n"
            "   50 anothercmd\n" % (command, command, command)
        )

        mock_run_command = self.patch(ps_module, "run_command")
        mock_run_command.return_value = Mock(stdout=ps_output, returncode=0)

        mock_running_in_container = self.patch(
            ps_module, "running_in_container"
        )
        mock_running_in_container.return_value = False

        mock_is_pid_in_container = self.patch(ps_module, "is_pid_in_container")
        mock_is_pid_in_container.side_effect = (
            lambda pid, proc_path: pid == 30
        )  # Simulate PID 30 is in a container

        result = get_running_pids_with_command(command)

        self.assertCountEqual(result, [20, 40])

        mock_run_command.assert_called_once_with("ps", "-eo", "pid,comm")

    def test_returns_processes_when_running_in_container(self):
        command = factory.make_name("command")

        ps_output = (
            "  PID COMMAND\n"
            "   10 %s\n"
            "   20 %s\n"
            "   30 %s\n"
            "   40 othercmd\n"
            "   50 anothercmd\n" % (command, command, command)
        )

        mock_run_command = self.patch(ps_module, "run_command")
        mock_run_command.return_value = Mock(stdout=ps_output, returncode=0)

        mock_running_in_container = self.patch(
            ps_module, "running_in_container"
        )
        mock_running_in_container.return_value = True

        mock_is_pid_in_container = self.patch(ps_module, "is_pid_in_container")

        result = get_running_pids_with_command(command)

        self.assertCountEqual(result, [10, 20, 30])

        mock_run_command.assert_called_once_with("ps", "-eo", "pid,comm")
        mock_is_pid_in_container.assert_not_called()
