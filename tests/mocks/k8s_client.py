# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from dataclasses import dataclass

from kubernetes.client.rest import ApiException


class K8sResource:
    """Track the current state of the resource"""

    def __init__(self, env: dict):
        self.env = env
        self.kernel_id: str = env.get("KERNEL_ID")
        self.kernel_username: str = env.get("KERNEL_USERNAME")
        self.pod_name = f"{self.kernel_username}-{self.kernel_id}"
        self.namespace: str = env.get("KERNEL_NAMESPACE")
        self.status: str = "Pending"
        self.query_counter: int = 1


k8s_resources: dict = {}


@dataclass
class MockPodStatus:
    pod_ip: str
    host_ip: str
    phase: str


@dataclass
class MockPodMetadata:
    name: str


@dataclass
class MockPodInfo:
    status: MockPodStatus
    metadata: MockPodMetadata


class MockResponse:
    def __init__(self, pod_info: MockPodInfo):
        self.items: list[MockPodInfo] = []
        self.items.append(pod_info)


class MockCoreV1Api:
    def list_namespaced_pod(self, namespace, **kwargs):
        kernel_id: str = ""
        label_selector = kwargs.get("label_selector", "")
        selector_entries = label_selector.split(",")
        for entry in selector_entries:
            if entry.startswith("kernel_id="):
                kernel_id = entry.split("=")[1]
                break
        if kernel_id in k8s_resources:
            resource = k8s_resources.get(kernel_id)
            if resource.query_counter >= 3:  # time to return
                resource.status = "Running"
                pod_info = MockPodInfo(
                    status=MockPodStatus("127.0.0.1", "127.0.0.1", resource.status),
                    metadata=MockPodMetadata(name=resource.pod_name),
                )
                response = MockResponse(pod_info=pod_info)
                return response
            else:
                resource.status = "Pending"
                resource.query_counter += 1

        return None

    def delete_namespaced_pod(self, name, namespace, **kwargs):
        pod_info = None
        delete_resource = None
        for kid, resource in k8s_resources.items():
            if resource.pod_name == name:
                resource.status = "Terminating"
                delete_resource = kid
                pod_info = MockPodInfo(
                    status=MockPodStatus("127.0.0.1", "127.0.0.1", resource.status),
                    metadata=MockPodMetadata(name=resource.pod_name),
                )
                break

        if pod_info:
            k8s_resources.pop(delete_resource)
            return pod_info

        raise ApiException(status=404, reason="Could not find resource with pod-name: '{name}'!")

    def delete_namespace(self, name, body):
        # TODO - add impl when adding namespace lifecycle testing
        pass

    def create_namespace(self, body):
        # TODO - add impl when adding namespace lifecycle testing
        pass


class MockRbacAuthorizationV1Api:
    def create_namespaced_role_binding(self, namespace, body):
        # TODO - add impl when adding namespace lifecycle testing
        pass


class MockK8sClient:
    def __init__(self, **kwargs):
        self.args = kwargs

    @classmethod
    def CoreV1Api(cls):
        return MockCoreV1Api()

    @classmethod
    def RbacAuthorizationV1Api(cls):
        return MockRbacAuthorizationV1Api()

    @classmethod
    def V1DeleteOptions(cls, grace_period_seconds=0, propagation_policy="Background") -> dict:
        return {"grace_period_seconds": 0, "propagation_policy": "Background"}

    @classmethod
    def V1ObjectMeta(cls, name, labels) -> dict:
        pass

    @classmethod
    def V1Namespace(cls, metadata) -> dict:
        pass

    @classmethod
    def V1RoleRef(cls, api_group, name) -> dict:
        pass

    @classmethod
    def V1Subject(cls, api_group, kind, name, namespace) -> dict:
        pass

    @classmethod
    def V1RoleBinding(cls, kind, metadata, role_ref, subjects) -> dict:
        pass
