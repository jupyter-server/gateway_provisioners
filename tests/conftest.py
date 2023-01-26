# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
import sys
from socket import socket

import pytest
import yarn_api_client

os.environ["PYTEST_CURRENT_TEST"] = "1"
os.environ["JUPYTER_PLATFORM_DIRS"] = "1"  # Avoid deprecation warning and use the platform dirs now

# See compatibility note on `group` keyword in https://docs.python.org/3/library/importlib.metadata.html#entry-points
if sys.version_info < (3, 10):  # pragma: no cover
    from importlib_metadata import EntryPoint, entry_points
else:  # pragma: no cover
    from importlib.metadata import EntryPoint, entry_points
from docker.client import DockerClient
from jupyter_client.kernelspec import KernelSpec
from jupyter_client.provisioning.factory import KernelProvisionerFactory
from mocks.docker_client import mock_docker_from_env
from mocks.k8s_client import MockK8sClient
from mocks.popen import mock_launch_kernel
from mocks.response_manager import mock_get_connection_info, mock_register_event, mock_socket_listen
from mocks.yarn_client import MockResourceManager

import gateway_provisioners
from gateway_provisioners.k8s import client  # noqa: F401
from gateway_provisioners.remote_provisioner import RemoteProvisionerBase
from gateway_provisioners.response_manager import ResponseManager


@pytest.fixture
def response_manager(monkeypatch):
    """Setup the Kernel Provisioner Factory, mocking the entrypoint fetch calls."""
    monkeypatch.setattr(ResponseManager, "register_event", mock_register_event)
    monkeypatch.setattr(socket, "listen", mock_socket_listen)
    monkeypatch.setattr(ResponseManager, "get_connection_info", mock_get_connection_info)
    rm = ResponseManager.instance()
    yield rm
    ResponseManager.clear_instance()


@pytest.fixture
def init_api_mocks(monkeypatch):
    monkeypatch.setattr(DockerClient, "from_env", mock_docker_from_env)
    monkeypatch.setattr(yarn_api_client.resource_manager, "ResourceManager", MockResourceManager)
    monkeypatch.setattr(
        gateway_provisioners.remote_provisioner, "gp_launch_kernel", mock_launch_kernel
    )
    monkeypatch.setattr(gateway_provisioners.k8s, "client", MockK8sClient)


@pytest.fixture
def kernelspec():
    def _kernelspec(name: str) -> KernelSpec:
        kspec = KernelSpec()
        kspec.argv = [
            "--public-key:{public_key}",
            "--response-address:{response_address}",
            "--port-range:{port_range}",
            "--kernel-id:{kernel_id}",
        ]
        kspec.display_name = f"{name}_python"
        kspec.language = "python"
        kspec.env = {}
        kspec.metadata = {}
        return kspec

    return _kernelspec


@pytest.fixture
def get_provisioner(kernelspec):
    def _get_provisioner(name: str, kernel_id: str) -> RemoteProvisionerBase:
        provisioner_config = {}
        provisioner_name = name + "-provisioner"
        eps = entry_points(group=KernelProvisionerFactory.GROUP_NAME, name=provisioner_name)
        assert eps, f"No entry_point was returned for provisioner '{provisioner_name}'!"
        ep: EntryPoint = eps[provisioner_name]
        provisioner_class = ep.load()
        provisioner: RemoteProvisionerBase = provisioner_class(
            kernel_id=kernel_id, kernel_spec=kernelspec(name), parent=None, **provisioner_config
        )
        return provisioner

    return _get_provisioner
