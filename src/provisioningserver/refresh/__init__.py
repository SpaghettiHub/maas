# Copyright 2016-2020 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functionality to refresh rack controller hardware and networking details."""

import copy
import os
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired
import tempfile
import urllib

from provisioningserver.logger import get_maas_logger
from provisioningserver.path import get_maas_data_path
from provisioningserver.refresh.maas_api_helper import (
    capture_script_output,
    Credentials,
    MD_VERSION,
    signal,
    SignalException,
)
from provisioningserver.refresh.node_info_scripts import NODE_INFO_SCRIPTS
from provisioningserver.utils.snap import running_in_snap
from provisioningserver.utils.twisted import synchronous

maaslog = get_maas_logger("refresh")


def signal_wrapper(*args, **kwargs):
    """Wrapper to capture and log any SignalException from signal."""
    try:
        signal(*args, **kwargs)
    except SignalException as e:
        maaslog.error("Error during controller refresh: %s" % e)


@synchronous
def refresh(
    system_id,
    consumer_key,
    token_key,
    token_secret,
    maas_url=None,
    post_process_hook=None,
):
    """Run all builtin commissioning scripts and report results to region."""
    maaslog.info("Refreshing rack controller hardware information.")

    if maas_url is None:
        maas_url = "http://127.0.0.1:5240/MAAS"
    url = f"{maas_url}/metadata/{MD_VERSION}/"

    creds = Credentials(
        token_key=token_key,
        token_secret=token_secret,
        consumer_key=consumer_key,
    )
    scripts = {
        name: config
        for name, config in NODE_INFO_SCRIPTS.items()
        if config["run_on_controller"]
    }

    with tempfile.TemporaryDirectory(
        prefix="maas-commission-", dir=get_maas_data_path("")
    ) as tmpdir:
        failed_scripts = runscripts(
            scripts,
            url,
            creds,
            tmpdir=tmpdir,
            post_process_hook=post_process_hook,
        )

    if failed_scripts:
        signal_wrapper(url, creds, "FAILED", f"Failed refreshing {system_id}")
    else:
        signal_wrapper(url, creds, "OK", f"Finished refreshing {system_id}")


SCRIPTS_BASE_PATH = os.path.dirname(__file__)


# XXX: This method should download the scripts from the region, instead
# of relying on the scripts being available locally.
def runscripts(scripts, url, creds, tmpdir, post_process_hook=None):
    in_snap = running_in_snap()

    total_scripts = len(scripts)
    current_script = 1
    failed_scripts = []
    out_dir = os.path.join(tmpdir, "out")
    os.makedirs(out_dir)
    fd, resources_file = tempfile.mkstemp()
    os.close(fd)
    for script_name in sorted(scripts.keys()):
        signal_wrapper(
            url,
            creds,
            "WORKING",
            f"Starting {script_name} [{current_script}/{total_scripts}]",
        )

        script_path = os.path.join(SCRIPTS_BASE_PATH, script_name)
        combined_path = os.path.join(out_dir, script_name)
        stdout_name = f"{script_name}.out"
        stdout_path = os.path.join(out_dir, stdout_name)
        stderr_name = f"{script_name}.err"
        stderr_path = os.path.join(out_dir, stderr_name)
        result_name = f"{script_name}.yaml"
        result_path = os.path.join(out_dir, result_name)

        # derive the base URL for from the metadata one
        parsed_url = urllib.parse.urlparse(url)
        base_url = urllib.parse.urlunparse(
            (parsed_url.scheme, parsed_url.netloc, "", "", "", "")
        )

        env = copy.deepcopy(os.environ)
        env.update(
            {
                "MAAS_BASE_URL": base_url,
                "MAAS_RESOURCES_FILE": resources_file,
                "OUTPUT_COMBINED_PATH": combined_path,
                "OUTPUT_STDOUT_PATH": stdout_path,
                "OUTPUT_STDERR_PATH": stderr_path,
                "RESULT_PATH": result_path,
                "TMPDIR": tmpdir,
            }
        )
        timeout = 60
        command = [script_path] if in_snap else ["sudo", "-E", script_path]
        try:
            proc = Popen(
                command, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, env=env
            )
            capture_script_output(
                proc, combined_path, stdout_path, stderr_path, timeout
            )
        except OSError as e:
            if isinstance(e.errno, int) and e.errno != 0:
                exit_status = e.errno
            else:
                # 2 is the return code bash gives when it can't execute.
                exit_status = 2
            result = str(e).encode()
            if result == b"":
                result = b"Unable to execute script"
            files = {script_name: result, stderr_name: result}
            signal_wrapper(
                url,
                creds,
                "WORKING",
                files=files,
                exit_status=exit_status,
                error="Failed to execute %s [%d/%d]: %d"
                % (script_name, current_script, total_scripts, exit_status),
            )
            failed_scripts.append(script_name)
        except TimeoutExpired:
            files = {
                script_name: open(combined_path, "rb").read(),
                stdout_name: open(stdout_path, "rb").read(),
                stderr_name: open(stderr_path, "rb").read(),
            }
            signal_wrapper(
                url,
                creds,
                "TIMEDOUT",
                files=files,
                error="Timeout(%s) expired on %s [%d/%d]"
                % (str(timeout), script_name, current_script, total_scripts),
            )
            failed_scripts.append(script_name)
        else:
            if post_process_hook is not None:
                post_process_hook(
                    script_name, combined_path, stdout_path, stderr_path
                )
            files = {
                script_name: open(combined_path, "rb").read(),
                stdout_name: open(stdout_path, "rb").read(),
                stderr_name: open(stderr_path, "rb").read(),
            }
            if os.path.exists(result_path):
                files[result_name] = open(result_path, "rb").read()
            signal_wrapper(
                url,
                creds,
                "WORKING",
                files=files,
                exit_status=proc.returncode,
                error="Finished %s [%d/%d]: %d"
                % (
                    script_name,
                    current_script,
                    total_scripts,
                    proc.returncode,
                ),
            )
            if proc.returncode != 0:
                failed_scripts.append(script_name)

        current_script += 1

    os.unlink(resources_file)
    return failed_scripts
