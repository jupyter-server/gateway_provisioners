# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from uuid import uuid4

import pytest

import gateway_provisioners
from gateway_provisioners.distributed import DistributedProvisioner


@pytest.mark.parametrize("gss_supported", [True, False])
def test_gss_requires_paramiko_with_gss_support(monkeypatch, gss_supported):
    """`GP_REMOTE_GSS_SSH` is rejected up front when paramiko has no GSS-API support."""
    monkeypatch.setattr(gateway_provisioners.distributed, "paramiko_supports_gss", gss_supported)
    monkeypatch.setenv("GP_REMOTE_GSS_SSH", "True")
    monkeypatch.delenv("GP_REMOTE_USER", raising=False)
    monkeypatch.delenv("GP_REMOTE_PWD", raising=False)

    if gss_supported:
        provisioner = DistributedProvisioner(kernel_id=str(uuid4()))
        assert provisioner.use_gss is True
        assert provisioner.remote_user is None
    else:
        with pytest.raises(RuntimeError, match="does not support GSS-API"):
            DistributedProvisioner(kernel_id=str(uuid4()))
