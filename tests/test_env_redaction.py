# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Tests ensuring kernel environment values are never written to logs unless allowlisted."""

import logging
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from validators import TEST_USER

from gateway_provisioners.distributed import DistributedProvisioner
from gateway_provisioners.remote_provisioner import (
    RemoteProvisionerBase,
    env_log_allowlist,
    redact_env,
)

BOOTSTRAP_SCRIPT = (
    Path(__file__).parent.parent
    / "gateway_provisioners"
    / "kernel-launchers"
    / "bootstrap"
    / "bootstrap-kernel.sh"
)
BASH = shutil.which("bash")

# Values that must never reach a log.  The multi-line value is matched on a fragment because
# repr() escapes its newlines, so the full value would never match even when leaked.
SECRET_ENV = {
    "AWS_SECRET_ACCESS_KEY": "aws-secret-value-1234",
    "KERNEL_EXTRA_TOKEN": "kernel-token-value-5678",
    "KERNEL_EXTRA_SPARK_OPTS": "--conf spark.hadoop.fs.s3a.secret.key=s3a-secret-value",
    "SSH_PRIVATE_KEY": "-----BEGIN KEY-----\nmultiline-secret-body\n-----END KEY-----",
    "GP_REMOTE_PWD": "remote-pwd-value",
}
SECRET_FRAGMENTS = [
    "aws-secret-value-1234",
    "kernel-token-value-5678",
    "s3a-secret-value",
    "multiline-secret-body",
    "remote-pwd-value",
]


def _assert_no_secret_logged(records: list[logging.LogRecord]) -> None:
    for record in records:
        message = record.getMessage()
        for fragment in SECRET_FRAGMENTS:
            assert fragment not in message, f"Secret value leaked into log: {message!r}"


def _messages_containing(records: list[logging.LogRecord], text: str) -> list[str]:
    return [record.getMessage() for record in records if text in record.getMessage()]


@pytest.mark.parametrize(
    "name,value,expected",
    [
        ("KERNEL_ID", "abc-123", "abc-123"),
        ("KERNEL_USERNAME", "alice", "alice"),
        ("KERNEL_POD_NAME", "alice-abc-123", "alice-abc-123"),
        ("AWS_SECRET_ACCESS_KEY", "aws-secret", "***"),
        ("KERNEL_EXTRA_TOKEN", "token", "***"),  # The KERNEL_ prefix alone is not trusted
        ("KERNEL_EXTRA_SPARK_OPTS", "--conf a.secret=b", "***"),
        ("GP_YARN_ENDPOINT", "http://user:pass@rm:8088", "***"),
        ("SSH_PRIVATE_KEY", "line1\nline2", "***"),
    ],
)
def test_redact_env_masks_values_not_allowlisted(name, value, expected):
    assert redact_env({name: value}) == {name: expected}


def test_redact_env_sorts_names_and_leaves_input_untouched():
    env = {"ZZZ_SECRET": "z", "KERNEL_ID": "abc", "AAA_SECRET": "a"}
    original = dict(env)

    redacted = redact_env(env)

    assert list(redacted) == ["AAA_SECRET", "KERNEL_ID", "ZZZ_SECRET"]
    assert redacted == {"AAA_SECRET": "***", "KERNEL_ID": "abc", "ZZZ_SECRET": "***"}
    assert env == original


def test_redact_env_handles_empty_env():
    assert redact_env({}) == {}


def test_env_log_allowlist_excludes_credential_like_names():
    """Guards the allowlist against entries whose values commonly carry credentials."""
    risky = re.compile(r"OPTS|ARGS|TOKEN|SECRET|PASSWORD|PWD|KEY|CREDENTIAL|URL|ENDPOINT")
    assert not [name for name in env_log_allowlist if risky.search(name)]


@pytest.mark.parametrize(
    "name,allowlisted_names",
    [
        ("docker", ["KERNEL_UID", "KERNEL_GID", "GP_DOCKER_MODE"]),
        ("kubernetes", ["KERNEL_NAMESPACE", "KERNEL_POD_NAME", "KERNEL_SERVICE_ACCOUNT_NAME"]),
    ],
)
async def test_launch_does_not_log_env_values(
    init_api_mocks, response_manager, get_provisioner, caplog, name, allowlisted_names
):
    kernel_id = str(uuid4())
    provisioner = get_provisioner(name, kernel_id)
    env = {"KERNEL_USERNAME": TEST_USER, **SECRET_ENV}

    with caplog.at_level(logging.DEBUG, logger=provisioner.log.name):
        kwargs = await provisioner.pre_launch(env=env)
        cmd = kwargs.pop("cmd")
        await provisioner.launch_kernel(cmd, **kwargs)
    await provisioner.terminate()
    await provisioner.cleanup(restart=False)

    _assert_no_secret_logged(caplog.records)

    launched_env = kwargs["env"]
    base_names = ["KERNEL_ID", "KERNEL_USERNAME", "KERNEL_LANGUAGE"]
    # Provisioner-specific entries are added after the base class logs from pre_launch().
    for method, logged_names in (
        ("pre_launch", base_names),
        ("launch_kernel", [*base_names, *allowlisted_names]),
    ):
        env_messages = _messages_containing(caplog.records, f"{method}() env:")
        assert len(env_messages) == 1, f"Expected one env log message from {method}()"
        message = env_messages[0]
        # Names (but not values) of secrets are retained to aid troubleshooting.
        for secret_name in ("AWS_SECRET_ACCESS_KEY", "KERNEL_EXTRA_TOKEN", "SSH_PRIVATE_KEY"):
            assert secret_name in message
        # GP_REMOTE_PWD is still dropped from the kernel env altogether.
        assert "GP_REMOTE_PWD" not in message
        for logged_name in logged_names:
            assert f"'{logged_name}': '{launched_env[logged_name]}'" in message


async def test_distributed_launch_does_not_log_env_values(
    response_manager, get_provisioner, caplog, monkeypatch
):
    async def mock_confirm_remote_startup(self):
        pass

    # Avoid spawning the kernel: only the logging performed by launch_kernel() is under test.
    monkeypatch.setattr(DistributedProvisioner, "_launch_remote_process", lambda *_, **__: "42")
    monkeypatch.setattr(
        DistributedProvisioner, "confirm_remote_startup", mock_confirm_remote_startup
    )
    kernel_id = str(uuid4())
    provisioner = get_provisioner("distributed", kernel_id)
    env = {"KERNEL_USERNAME": TEST_USER, "KERNEL_ID": kernel_id, **SECRET_ENV}

    with caplog.at_level(logging.DEBUG, logger=provisioner.log.name):
        await provisioner.launch_kernel(["run.sh"], env=env, kernel_id=kernel_id)
    await provisioner.cleanup(restart=False)

    _assert_no_secret_logged(caplog.records)

    env_messages = _messages_containing(
        caplog.records, "DistributedProvisioner.launch_kernel() env:"
    )
    assert len(env_messages) == 1
    assert "AWS_SECRET_ACCESS_KEY" in env_messages[0]
    assert f"'KERNEL_ID': '{kernel_id}'" in env_messages[0]
    assert f"'KERNEL_USERNAME': '{TEST_USER}'" in env_messages[0]


async def test_distributed_remote_launch_does_not_log_kernelspec_env(
    response_manager, get_provisioner, caplog, monkeypatch
):
    """SSH launches embed the kernelspec's env values in the startup command they assemble."""

    async def mock_confirm_remote_startup(self):
        pass

    def mock_rsh(self, host, command):
        return ["4242"]  # The remote shell echoes the launched process id

    # Take the SSH launch path without connecting anywhere: the startup command is still built
    # from the kernelspec, only the remote shell is replaced.
    monkeypatch.setattr(RemoteProvisionerBase, "ip_is_local", staticmethod(lambda ip: False))
    monkeypatch.setattr(DistributedProvisioner, "_rsh", mock_rsh)
    monkeypatch.setattr(
        DistributedProvisioner, "confirm_remote_startup", mock_confirm_remote_startup
    )
    kernel_id = str(uuid4())
    provisioner = get_provisioner("distributed", kernel_id)
    provisioner.kernel_spec.env = {
        "AWS_SECRET_ACCESS_KEY": SECRET_ENV["AWS_SECRET_ACCESS_KEY"],
        "SPARK_OPTS": SECRET_ENV["KERNEL_EXTRA_SPARK_OPTS"],
    }
    env = {"KERNEL_USERNAME": TEST_USER, "KERNEL_ID": kernel_id}

    with caplog.at_level(logging.DEBUG, logger=provisioner.log.name):
        await provisioner.launch_kernel(["run.sh"], env=env, kernel_id=kernel_id)
    await provisioner.cleanup(restart=False)

    assert provisioner.pid == 4242  # The SSH launch path was taken
    _assert_no_secret_logged(caplog.records)
    assert _messages_containing(
        caplog.records, f"Invoking kernel launch on host: {provisioner.assigned_host}"
    )


@pytest.mark.skipif(BASH is None, reason="bash is required")
def test_bootstrap_kernel_prints_only_env_names():
    # Without KERNEL_LANGUAGE, the script exits right after printing its environment.
    env = {"PATH": "/usr/bin:/bin", **SECRET_ENV}
    result = subprocess.run(  # noqa: S603
        [BASH, str(BOOTSTRAP_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 1
    assert "KERNEL_LANGUAGE is required" in result.stdout
    output = result.stdout + result.stderr
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in output
    for secret_name in SECRET_ENV:
        assert secret_name in output
