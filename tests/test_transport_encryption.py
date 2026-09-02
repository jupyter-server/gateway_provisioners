# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Tests for the CurveZMQ transport-encryption support in RemoteProvisionerBase."""

import logging
import re
from uuid import uuid4

import pytest
import zmq
from jupyter_client.connect import ConnectionFileMixin
from jupyter_client.manager import KernelManager
from jupyter_client.provisioning.provisioner_base import KernelProvisionerBase

# Whether this environment can apply curve encryption on the server side.  The second
# condition requires jupyter_client >= 8.9.
CURVE_AVAILABLE = zmq.has("curve") and hasattr(ConnectionFileMixin, "curve_publickey")


@pytest.fixture
def provisioner(init_api_mocks, response_manager, get_provisioner):
    return get_provisioner("docker", str(uuid4()))


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({}, False),
        ({"supported_encryption": ["curve"]}, True),
        ({"supported_encryption": "curve"}, True),
        ({"supported_encryption": ["CURVE"]}, True),
        ({"supported_encryption": ["tls"]}, False),
        ({"supported_encryption": None}, False),
    ],
)
def test_kernel_spec_supports_curve(provisioner, metadata, expected):
    provisioner.kernel_spec.metadata = metadata
    assert provisioner._kernel_spec_supports_curve() is expected


def test_resolve_defaults_to_disabled(provisioner):
    provisioner._resolve_transport_encryption(None)
    assert provisioner.transport_encryption == "disabled"
    assert provisioner.curve_enabled is False


def test_resolve_rejects_invalid_policy(provisioner):
    with pytest.raises(ValueError, match="Invalid transport_encryption value"):
        provisioner._resolve_transport_encryption("bogus")


def test_resolve_auto_without_spec_support(provisioner):
    provisioner.kernel_spec.metadata = {}
    provisioner._resolve_transport_encryption("auto")
    assert provisioner.transport_encryption == "auto"
    assert provisioner.curve_enabled is False


def test_resolve_required_without_spec_support(provisioner):
    provisioner.kernel_spec.metadata = {}
    with pytest.raises(RuntimeError, match="does not declare 'curve'"):
        provisioner._resolve_transport_encryption("required")


def test_resolve_auto_with_spec_support(provisioner):
    provisioner.kernel_spec.metadata = {"supported_encryption": ["curve"]}
    provisioner._resolve_transport_encryption("auto")
    assert provisioner.curve_enabled is CURVE_AVAILABLE


def test_resolve_required_with_spec_support(provisioner):
    provisioner.kernel_spec.metadata = {"supported_encryption": ["curve"]}
    if CURVE_AVAILABLE:
        provisioner._resolve_transport_encryption("required")
        assert provisioner.curve_enabled is True
    else:
        with pytest.raises(RuntimeError, match="cannot be applied"):
            provisioner._resolve_transport_encryption("required")


def test_response_validation_required_missing_keys(provisioner):
    provisioner.transport_encryption = "required"
    provisioner.curve_enabled = True
    with pytest.raises(RuntimeError, match="did not return valid CurveZMQ keys"):
        provisioner._validate_transport_encryption_response({})


def test_response_validation_auto_missing_keys_warns(provisioner, caplog):
    provisioner.transport_encryption = "auto"
    provisioner.curve_enabled = True
    with caplog.at_level(logging.WARNING, logger=provisioner.log.name):
        provisioner._validate_transport_encryption_response({})
    assert any("did not return valid CurveZMQ keys" in record.message for record in caplog.records)


def test_response_validation_accepts_returned_keys(provisioner):
    provisioner.transport_encryption = "required"
    provisioner.curve_enabled = True
    provisioner._validate_transport_encryption_response(
        {"curve_publickey": "A" * 40, "curve_secretkey": "B" * 40}
    )


def test_response_validation_rejects_malformed_keys(provisioner):
    # Presence is not validity: malformed keys would otherwise fail later inside
    # pyzmq (ZMQError: Invalid argument) after the launch was reported successful.
    provisioner.transport_encryption = "required"
    provisioner.curve_enabled = True
    with pytest.raises(RuntimeError, match="did not return valid CurveZMQ keys"):
        provisioner._validate_transport_encryption_response(
            {"curve_publickey": "pub", "curve_secretkey": "sec"}
        )


def test_response_validation_purges_malformed_keys_under_auto(provisioner):
    provisioner.transport_encryption = "auto"
    provisioner.curve_enabled = True
    connect_info = {"shell_port": 1, "curve_publickey": "pub", "curve_secretkey": ""}
    provisioner._validate_transport_encryption_response(connect_info)
    assert "curve_publickey" not in connect_info
    assert "curve_secretkey" not in connect_info


def test_response_validation_clears_stale_parent_traits(provisioner):
    km = KernelManager()
    km.curve_publickey = b"stale-pub"
    km.curve_secretkey = b"stale-sec"
    provisioner.parent = km
    provisioner._validate_transport_encryption_response({})
    assert km.curve_publickey is None
    assert km.curve_secretkey is None


def test_response_validation_keeps_parent_traits_when_keys_returned(provisioner):
    km = KernelManager()
    km.curve_publickey = b"A" * 40
    km.curve_secretkey = b"B" * 40
    provisioner.parent = km
    provisioner._validate_transport_encryption_response(
        {"curve_publickey": "A" * 40, "curve_secretkey": "B" * 40}
    )
    assert km.curve_publickey == b"A" * 40
    assert km.curve_secretkey == b"B" * 40


async def test_pre_launch_substitutes_transport_encryption(provisioner):
    provisioner.kernel_spec.metadata = {"supported_encryption": ["curve"]}
    kwargs = await provisioner.pre_launch(env={}, transport_encryption="auto")
    cmd = kwargs.get("cmd")
    assert "transport_encryption" not in kwargs
    if CURVE_AVAILABLE:
        assert "--transport-encryption:auto" in cmd
    else:
        assert "--transport-encryption:" in cmd


async def test_pre_launch_substitutes_empty_when_disabled(provisioner):
    kwargs = await provisioner.pre_launch(env={})
    cmd = kwargs.get("cmd")
    assert "--transport-encryption:" in cmd
    assert not any(arg.startswith("--transport-encryption:{") for arg in cmd)


def test_connection_info_is_not_shared_between_provisioners(
    init_api_mocks, response_manager, get_provisioner
):
    # KernelProvisionerBase.connection_info is a mutable class attribute; without per-instance
    # rebinding, one kernel's curve keys would leak into every other kernel's connection info.
    p1 = get_provisioner("docker", str(uuid4()))
    p2 = get_provisioner("docker", str(uuid4()))
    assert p1.connection_info is not p2.connection_info
    p1._update_connection({"curve_publickey": "A" * 40, "curve_secretkey": "B" * 40})
    assert p2.connection_info == {}
    assert KernelProvisionerBase.connection_info == {}


def test_response_validation_drops_half_key_response(provisioner):
    # A response with only one curve field must fall back to plaintext, not fail
    # reconciliation against the manager's (empty) curve state.
    provisioner.transport_encryption = "auto"
    provisioner.curve_enabled = True
    connect_info = {"shell_port": 1, "curve_publickey": "A" * 40}
    provisioner._validate_transport_encryption_response(connect_info)
    assert "curve_publickey" not in connect_info


def test_response_validation_purges_stale_connection_info_keys(provisioner):
    # A restart that falls back to plaintext must remove the previous launch's keys from the
    # provisioner's connection info, else reconciliation re-applies them on the manager.
    provisioner.connection_info.update({"curve_publickey": "A" * 40, "curve_secretkey": "B" * 40})
    provisioner.transport_encryption = "auto"
    provisioner.curve_enabled = True
    provisioner._validate_transport_encryption_response({"shell_port": 1})
    assert "curve_publickey" not in provisioner.connection_info
    assert "curve_secretkey" not in provisioner.connection_info


def test_resolve_auto_without_placeholder_warns(provisioner, caplog):
    # A kernelspec generated before transport encryption, with 'curve' added to its metadata
    # by hand: the launcher is never asked for keys, so the diagnostic must name the argv
    # placeholder instead of blaming the launcher or the kernel image.
    provisioner.kernel_spec.metadata = {"supported_encryption": ["curve"]}
    provisioner.kernel_spec.argv = ["--kernel-id:{kernel_id}"]
    with caplog.at_level(logging.WARNING, logger=provisioner.log.name):
        provisioner._resolve_transport_encryption("auto")
    assert provisioner.curve_enabled is False
    assert any("'{transport_encryption}' placeholder" in r.message for r in caplog.records)
    # Nothing was requested from the launcher, so the response validation stays quiet.
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=provisioner.log.name):
        provisioner._validate_transport_encryption_response({})
    assert not any("did not return valid CurveZMQ keys" in r.message for r in caplog.records)


def test_resolve_required_without_placeholder_raises(provisioner):
    provisioner.kernel_spec.metadata = {"supported_encryption": ["curve"]}
    provisioner.kernel_spec.argv = ["--kernel-id:{kernel_id}"]
    with pytest.raises(RuntimeError, match=re.escape("no '{transport_encryption}' placeholder")):
        provisioner._resolve_transport_encryption("required")
    assert provisioner.curve_enabled is False
