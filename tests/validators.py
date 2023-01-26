# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from typing import Optional

from jupyter_client.kernelspec import KernelSpec
from mocks.response_manager import generate_connection_info

from gateway_provisioners.remote_provisioner import RemoteProvisionerBase
from gateway_provisioners.response_manager import ResponseManager

# warning including YarnProvisioner will break the mock of the Yarn ResourceManager

TEST_USER = "test-user"


class ValidatorBase:
    @classmethod
    def create_instance(cls, name: str, seed_env: dict, **kwargs):
        if name == "kubernetes":
            return K8sValidator(name=name, seed_env=seed_env, **kwargs)
        if name == "yarn":
            return YarnValidator(name=name, seed_env=seed_env, **kwargs)
        if name == "docker":
            return DockerValidator(name=name, seed_env=seed_env, **kwargs)
        if name == "docker-swarm":
            return DockerSwarmValidator(name=name, seed_env=seed_env, **kwargs)
        err_msg = f"Invalid name '{name}' encountered!"
        raise AssertionError(err_msg)

    def __init__(self, name: str, seed_env: dict, **kwargs):
        self.name: str = name
        self.seed_env: dict = seed_env
        self.kernel_id: str = kwargs.get("kernel_id")
        self.response_manager: ResponseManager = kwargs.get("response_manager")
        self.kernel_spec: Optional[KernelSpec] = None
        self.provisioner = None

    def validate_provisioner(self, provisioner: RemoteProvisionerBase) -> None:
        assert provisioner.kernel_id == self.kernel_id
        assert provisioner.response_manager == self.response_manager
        assert not provisioner.kernel_username
        assert provisioner.kernel_spec.language == "python"
        self.kernel_spec = provisioner.kernel_spec
        self.provisioner = provisioner

    def validate_pre_launch(self, kwargs: dict) -> None:
        cmd: list = kwargs.get("cmd")
        assert cmd is not None
        assert f"--kernel-id:{self.kernel_id}" in cmd
        assert "--port-range:0..0" in cmd
        assert f"--response-address:{self.response_manager.response_address}" in cmd
        assert f"--public-key:{self.response_manager.public_key}" in cmd

        env: dict = kwargs.get("env")
        assert env is not None
        assert env["KERNEL_ID"] == self.kernel_id
        assert env["KERNEL_USERNAME"] == TEST_USER
        assert env["KERNEL_LANGUAGE"] == self.kernel_spec.language

    def validate_launch_kernel(self, connection_info: dict) -> None:
        assert connection_info == generate_connection_info(self.kernel_id)

    def validate_post_launch(self, kwargs: dict) -> None:
        """Not currently used by GP"""
        pass


class YarnValidator(ValidatorBase):
    """Handles validation of YarnProvisioners"""

    def validate_pre_launch(self, kwargs: dict):
        super().validate_pre_launch(kwargs)

        env: dict = kwargs.get("env")
        assert env["GP_IMPERSONATION_ENABLED"] == "False"
        assert self.provisioner.rm_addr == env["GP_YARN_ENDPOINT"]


class K8sValidator(ValidatorBase):
    """Handles validation of KubernetesProvisioners"""

    def validate_pre_launch(self, kwargs: dict):
        super().validate_pre_launch(kwargs)

        env: dict = kwargs.get("env")
        assert env["KERNEL_UID"] == "1000"
        assert env["KERNEL_GID"] == "100"
        assert env["KERNEL_POD_NAME"] == f"{TEST_USER}-{self.kernel_id}"
        assert env["KERNEL_NAMESPACE"] == "default"
        assert env["KERNEL_SERVICE_ACCOUNT_NAME"] == "default"


class DockerValidator(ValidatorBase):
    """Handles validation of DockerProvisioners"""

    def validate_pre_launch(self, kwargs: dict):
        super().validate_pre_launch(kwargs)

        env: dict = kwargs.get("env")
        assert env["KERNEL_UID"] == "1000"
        assert env["KERNEL_GID"] == "100"
        assert env["GP_DOCKER_NETWORK"] == "bridge"
        assert env["GP_DOCKER_MODE"] == "docker"


class DockerSwarmValidator(ValidatorBase):
    """Handles validation of DockerSwarmProvisioners"""

    def validate_pre_launch(self, kwargs: dict):
        super().validate_pre_launch(kwargs)

        env: dict = kwargs.get("env")
        assert env["KERNEL_UID"] == "1000"
        assert env["KERNEL_GID"] == "100"
        assert env["GP_DOCKER_NETWORK"] == "bridge"
        assert env["GP_DOCKER_MODE"] == "swarm"
