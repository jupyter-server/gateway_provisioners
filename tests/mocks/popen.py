# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from subprocess import Popen

from .docker_client import DockerResource, docker_resources
from .k8s_client import K8sResource, k8s_resources
from .yarn_client import YarnResource, yarn_resources


class MockPopen(Popen):
    def __init__(self, cmd: list, **kwargs):
        self.cmd = cmd
        self.args = kwargs
        self.env = kwargs.get("env")
        self.kernel_id = self.env.get("KERNEL_ID")
        self.resources = None
        self.pid = 42

    def wait(self, timeout=None):
        # This is called at cleanup and a good time to clear our resource cache
        assert self.resources
        self.resources.pop(self.kernel_id)
        return None

    def poll(self):
        # Ensure the resource still exits, else return non-None
        if self.resources and self.kernel_id in self.resources:
            return None
        return 2

    def mock_resources(self):
        """Sets up the initial resource (application, container) for discovery and state management"""
        if "GP_DOCKER_MODE" in self.env:  # This is docker, which one?
            resource = DockerResource(env=self.env)
            docker_resources[resource.kernel_id] = resource
            self.resources = docker_resources
        elif "KERNEL_POD_NAME" in self.env:  # This is k8s
            resource = K8sResource(env=self.env)
            k8s_resources[resource.kernel_id] = resource
            self.resources = k8s_resources
        elif "GP_IMPERSONATION_ENABLED" in self.env:  # This is yarn (but a little fragile)
            resource = YarnResource(env=self.env)
            yarn_resources[resource.kernel_id] = resource
            self.resources = yarn_resources
        else:
            err_msg = "Cant determine resource to mock!"
            raise AssertionError(err_msg)


def mock_launch_kernel(cmd: list, **kwargs) -> Popen:
    proc = MockPopen(cmd, **kwargs)
    proc.mock_resources()
    return proc
