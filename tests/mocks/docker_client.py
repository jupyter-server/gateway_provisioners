# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.


class DockerResource:
    """Track the current state of the resource"""

    def __init__(self, env: dict):
        self.env = env
        self.kernel_id: str = env.get("KERNEL_ID")
        self.kernel_username: str = env.get("KERNEL_USERNAME")
        self.container_name = f"{self.kernel_username}-{self.kernel_id}"
        self.docker_network = env.get("GP_DOCKER_NETWORK")
        self.is_swarm = env.get("GP_DOCKER_MODE") == "swarm"
        self.status: str = "created"
        if self.is_swarm:
            self.status = "preparing"
        self.query_counter: int = 1


docker_resources: dict = {}


class MockService:
    def __init__(self, resource: DockerResource):
        self.resource = resource
        self.name = resource.container_name
        self.status = resource.status
        self.attrs = {
            "NetworkSettings": {
                "IPAddress": "127.0.0.1",
                "Networks": {resource.docker_network: {"IPAddress": "127.0.0.1"}},
            }
        }
        task = {
            "ID": hash(self.resource.kernel_id),
            "Status": {"State": self.resource.status},
            "NetworksAttachments": [{"Addresses": ["127.0.0.1/xxx"]}],
        }
        self.task_list: list = [task]

    def tasks(self, **kwargs):
        return self.task_list

    def remove(self, **kwargs):
        docker_resources.pop(self.resource.kernel_id)


class MockServiceCollection:  # (ServiceCollection):
    def __init__(self, **kwargs):
        pass

    def list(self, **kwargs):
        """Get a collection of Containers"""
        # This will be called with a filters object, the "label" key of
        # which contains the kernel_id, so we need to pick that out to
        # locate the appropriate entry:
        # {"label": "kernel_id=" + self.kernel_id}"

        services = []
        label = kwargs.get("filters", {}).get("label", "")
        assert label, "No label found in filters - can't list containers!"
        kernel_id = label.split("=")[1]
        if kernel_id in docker_resources:
            resource = docker_resources.get(kernel_id)
            if resource.query_counter >= 3:  # time to return
                resource.status = "running"
                service = MockService(resource)
                services.append(service)
            else:
                resource.status = "starting"
            resource.query_counter += 1

        return services


class MockContainer:
    def __init__(self, resource: DockerResource):
        self.resource = resource
        self.name = resource.container_name
        self.status = resource.status
        self.attrs = {
            "NetworkSettings": {
                "IPAddress": "127.0.0.1",
                "Networks": {resource.docker_network: {"IPAddress": "127.0.0.1"}},
            }
        }

    def remove(self, **kwargs):
        docker_resources.pop(self.resource.kernel_id)


class MockContainerCollection:  # (ContainerCollection):
    def __init__(self, **kwargs):
        pass

    def list(self, **kwargs):
        """Get a collection of Containers"""
        # This will be called with a filters object, the "label" key of
        # which contains the kernel_id, so we need to pick that out to
        # locate the appropriate entry:
        # {"label": "kernel_id=" + self.kernel_id}"

        containers = []
        label = kwargs.get("filters", {}).get("label", "")
        assert label, "No label found in filters - can't list containers!"
        kernel_id = label.split("=")[1]
        if kernel_id in docker_resources:
            resource = docker_resources.get(kernel_id)
            if resource.query_counter >= 3:  # time to return
                resource.status = "running"
                container = MockContainer(resource)
                containers.append(container)
            resource.query_counter += 1

        return containers


class MockDockerClient:  # (DockerClient):
    def __init__(self, **kwargs):
        pass

    @property
    def containers(self):
        return MockContainerCollection(client=self)

    @property
    def services(self):
        return MockServiceCollection(client=self)


def mock_docker_from_env():  # -> DockerClient:
    return MockDockerClient()
