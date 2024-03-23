# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Code related to managing kernels running in docker-based containers."""
from __future__ import annotations

import logging
import os
from typing import Any

from overrides import overrides

try:
    from docker.client import DockerClient  # type:ignore[import-untyped]
    from docker.errors import NotFound  # type:ignore[import-untyped]
    from docker.models.containers import Container  # type:ignore[import-untyped]
    from docker.models.services import Service  # type:ignore[import-untyped]
except ImportError:
    logging.warning(
        "The extra package 'docker' is not installed in this environment and is required.  "
        "Ensure that gateway_provisioners is installed by specifying the extra 'docker' "
        "(e.g., pip install 'gateway_provisioners[docker]')."
    )
    raise

from .container import ContainerProvisionerBase

# Debug logging level of docker produces too much noise - raise to info by default.
logging.getLogger("urllib3.connectionpool").setLevel(
    os.environ.get("GP_DOCKER_LOG_LEVEL", logging.WARNING)
)

docker_network = os.environ.get("GP_DOCKER_NETWORK", "bridge")


class DockerSwarmProvisioner(ContainerProvisionerBase):
    """Kernel provisioner for kernels in Docker Swarm."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = DockerClient.from_env()

    @overrides
    async def pre_launch(self, **kwargs: Any) -> dict[str, Any]:
        kwargs = await super().pre_launch(**kwargs)

        # Convey the network to the docker launch script
        kwargs["env"]["GP_DOCKER_NETWORK"] = docker_network
        kwargs["env"]["GP_DOCKER_MODE"] = "swarm"
        return kwargs

    @overrides
    def get_initial_states(self) -> set[str]:
        return {"preparing", "starting", "running"}

    @overrides
    def get_error_states(self) -> set[str]:
        return {"failed", "rejected", "complete", "shutdown", "orphaned", "remove"}

    @overrides
    def get_container_status(self, iteration: str | None) -> str:
        # Locates the kernel container using the kernel_id filter.  If the status indicates an initial state we
        # should be able to get at the NetworksAttachments and determine the associated container's IP address.
        task_state = ""
        task_id = None
        task = self._get_task()
        if task:
            task_status = task["Status"]
            task_id = task["ID"]
            if task_status:
                task_state = task_status["State"].lower()
                if (
                    self.assigned_host == "" and task_state == "running"
                ):  # in self.get_initial_states():
                    # get the NetworkAttachments and pick out the first of the Network and first
                    networks_attachments = task["NetworksAttachments"]
                    if len(networks_attachments) > 0:
                        address = networks_attachments[0]["Addresses"][0]
                        ip = address.split("/")[0]
                        self.assigned_ip = ip
                        self.assigned_host = self.container_name

        if iteration:  # only log if iteration is not None (otherwise poll() is too noisy)
            self.log.debug(
                f"{iteration}: Waiting to connect to docker container. "
                f"Name: '{self.container_name}', Status: '{task_state}', "
                f"IPAddress: '{self.assigned_ip}', KernelID: '{self.kernel_id}', "
                f"TaskID: '{task_id}'"
            )
        return task_state

    @overrides
    def terminate_container_resources(self, restart: bool = False) -> bool | None:
        # Remove the docker service.

        result = True  # We'll be optimistic
        service = self._get_service()
        if service:
            try:
                service.remove()  # Service still exists, attempt removal
            except Exception as err:
                self.log.debug(
                    f"{self.__class__.__name__} Termination of service: "
                    f"{service.name} raised exception: {err}"
                )
                if isinstance(err, NotFound):
                    pass  # okay if its not found
                else:
                    result = False
                    self.log.warning(f"Error occurred removing service: {err}")
        if result:
            self.log.debug(
                f"{self.__class__.__name__}.terminate_container_resources, "
                f"service {self.container_name}, "
                f"kernel ID: {self.kernel_id} has been terminated."
            )
            self.container_name = None
            result = None  # maintain jupyter contract
        else:
            self.log.warning(
                f"{self.__class__.__name__}.terminate_container_resources, "
                f"container {self.container_name}, "
                f"kernel ID: {self.kernel_id} has not been terminated."
            )
        return result

    def _get_service(self) -> Service:
        """Fetches the service object corresponding to the kernel with a matching label."""
        service = None
        services = self.client.services.list(filters={"label": "kernel_id=" + self.kernel_id})
        num_services = len(services)
        if num_services != 1:
            if num_services > 1:
                err_msg = (
                    f"{self.__class__.__name__}: Found more than one service "
                    f"({num_services}) for kernel_id '{self.kernel_id}'!"
                )
                raise RuntimeError(err_msg)
        else:
            service = services[0]
            self.container_name = service.name
        return service

    def _get_task(self) -> dict | None:
        """
        Fetches the task object corresponding to the service associated with the kernel.  We only ask for the
        current task with desired-state == running.  This eliminates failed states.
        """
        task = None
        service = self._get_service()
        if service:
            tasks = service.tasks(filters={"desired-state": "running"})
            num_tasks = len(tasks)
            if num_tasks != 1:
                if num_tasks > 1:
                    err_msg = (
                        f"{self.__class__.__name__}: Found more than one task ({num_tasks}) "
                        f"for service '{service.name}', kernel_id '{self.kernel_id}'!"
                    )
                    raise RuntimeError(err_msg)
            else:
                task = tasks[0]
        return task


class DockerProvisioner(ContainerProvisionerBase):
    """Kernel provisioner for kernels in Docker (non-Swarm)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = DockerClient.from_env()

    @overrides
    async def pre_launch(self, **kwargs: Any) -> dict[str, Any]:
        kwargs = await super().pre_launch(**kwargs)

        # Convey the network to the docker launch script
        kwargs["env"]["GP_DOCKER_NETWORK"] = docker_network
        kwargs["env"]["GP_DOCKER_MODE"] = "docker"
        return kwargs

    @overrides
    def get_initial_states(self) -> set[str]:
        return {"created", "running"}

    @overrides
    def get_error_states(self) -> set[str]:
        return {"restarting", "removing", "paused", "exited", "dead"}

    @overrides
    def get_container_status(self, iteration: str | None) -> str:
        # Locates the kernel container using the kernel_id filter.  If the phase indicates Running, the pod's IP
        # is used for the assigned_ip.  Only used when docker mode == regular (non swarm)
        container_status = ""

        container = self._get_container()
        if container:
            self.container_name = container.name
            if container.status:
                container_status = container.status.lower()
                if container_status == "running" and self.assigned_host == "":
                    # Container is running, capture IP

                    # we'll use this as a fallback in case we don't find our network
                    self.assigned_ip = container.attrs.get("NetworkSettings").get("IPAddress")
                    networks = container.attrs.get("NetworkSettings").get("Networks")
                    if len(networks) > 0:
                        self.assigned_ip = networks.get(docker_network).get("IPAddress")
                        self.log.debug(
                            f"Using assigned_ip {self.assigned_ip} from docker network '{docker_network}'."
                        )
                    else:
                        self.log.warning(
                            f"Docker network '{docker_network}' could not be located in "
                            f"container attributes - using assigned_ip '{self.assigned_ip}'."
                        )

                    self.assigned_host = self.container_name

        if iteration:  # only log if iteration is not None (otherwise poll() is too noisy)
            self.log.debug(
                f"{iteration}: Waiting to connect to docker container. "
                f"Name: '{self.container_name}', Status: '{container_status}', "
                f"IPAddress: '{self.assigned_ip}', KernelID: '{self.kernel_id}'"
            )

        return container_status

    @overrides
    def terminate_container_resources(self, restart: bool = False) -> bool:
        # Remove the container

        result = True  # Since we run containers with remove=True, we'll be optimistic
        container = self._get_container()
        if container:
            try:
                container.remove(force=True)  # Container still exists, attempt forced removal
            except Exception as err:
                self.log.debug(
                    f"Container termination for container: {container.name} raised exception: {err}"
                )
                if isinstance(err, NotFound):
                    pass  # okay if its not found
                else:
                    result = False
                    self.log.warning(f"Error occurred removing container: {err}")

        if result:
            self.log.debug(
                f"{self.__class__.__name__}.terminate_container_resources, "
                f"container {self.container_name}, "
                f"kernel ID: {self.kernel_id} has been terminated."
            )
            self.container_name = None
            result = None  # maintain jupyter contract
        else:
            self.log.warning(
                f"{self.__class__.__name__}.terminate_container_resources, "
                f"container {self.container_name}, "
                f"kernel ID: {self.kernel_id} has not been terminated."
            )
        return result

    def _get_container(self) -> Container:
        # Fetches the container object corresponding the kernel_id label.
        # Only used when docker mode == regular (not swarm)

        container = None
        containers = self.client.containers.list(filters={"label": "kernel_id=" + self.kernel_id})
        num_containers = len(containers)
        if num_containers != 1:
            if num_containers > 1:
                err_msg = (
                    f"{self.__class__.__name__}: Found more than one container "
                    f"({num_containers}) for kernel_id '{self.kernel_id}'!"
                )
                raise RuntimeError(err_msg)
        else:
            container = containers[0]
        return container
