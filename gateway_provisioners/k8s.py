# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Code related to managing kernels running in Kubernetes clusters."""

import logging
import os
import re
from typing import Any, Dict, Optional, Set

import urllib3
from overrides import overrides

try:
    from jinja2 import Environment  # noqa - used by launcher so check presence here
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError:
    logging.warning(
        "At least one of the extra packages 'kubernetes' or 'jinja2' are not installed in "
        "this environment and are required.  Ensure that gateway_provisioners is installed "
        "by specifying the extra 'k8s' (e.g., pip install 'gateway_provisioners[k8s]')."
    )
    raise


from .container import ContainerProvisionerBase

urllib3.disable_warnings()

# Default logging level of kubernetes produces too much noise - raise to warning only.
logging.getLogger("kubernetes").setLevel(os.environ.get("EG_KUBERNETES_LOG_LEVEL", logging.WARNING))

k8s_provisioner_namespace = os.environ.get("GP_NAMESPACE", "default")
default_kernel_service_account_name = os.environ.get(
    "GP_DEFAULT_KERNEL_SERVICE_ACCOUNT_NAME", "default"
)
kernel_cluster_role = os.environ.get("GP_KERNEL_CLUSTER_ROLE", "cluster-admin")

# Since provisioners are a single-user scenario (not going through EG), use a shared namespace.
shared_namespace = bool(os.environ.get("GP_SHARED_NAMESPACE", "True").lower() == "true")
kpt_dir = os.environ.get("GP_POD_TEMPLATE_DIR", "/tmp")  # noqa: S108

app_name = os.environ.get("GP_APP_NAME", "k8s-provisioner")

if (
    "SPHINX_BUILD_IN_PROGRESS" not in os.environ
    and "PYTEST_CURRENT_TEST" not in os.environ
    and "PYTEST_RUN_CONFIG" not in os.environ
):
    if bool(os.environ.get("GP_USE_INCLUSTER_CONFIG", "True").lower() == "true"):
        config.load_incluster_config()
    else:
        config.load_kube_config()


class KubernetesProvisioner(ContainerProvisionerBase):
    """Kernel lifecycle management for Kubernetes kernels."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.kernel_pod_name = None
        self.kernel_namespace = None
        self.delete_kernel_namespace = False
        # Track if we're restarting the pod from this instance.  This will be
        # set to true when restarting kernels during the original pod's termination
        # and if the kernel resides in its own namespace.
        self.restarting = False

    @overrides
    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        # Set env before superclass call so we see these in the debug output

        # Kubernetes relies on many internal env variables.  Since we're running in a k8s pod, we will
        # transfer its env to each launched kernel.
        kwargs["env"] = dict(os.environ, **kwargs.get("env", {}))
        kwargs = await super().pre_launch(**kwargs)
        # These must follow call to super() so that kernel_username is established
        self.kernel_pod_name = self._determine_kernel_pod_name(**kwargs)
        self.kernel_namespace = self._determine_kernel_namespace(
            **kwargs
        )  # will create namespace if not provided
        return kwargs

    @overrides
    async def get_provisioner_info(self) -> Dict[str, Any]:
        provisioner_info = await super().get_provisioner_info()
        provisioner_info.update(
            {
                "kernel_ns": self.kernel_namespace,
                "delete_ns": self.delete_kernel_namespace,
            }
        )
        return provisioner_info

    @overrides
    async def load_provisioner_info(self, provisioner_info: dict) -> None:
        await super().load_provisioner_info(provisioner_info)
        self.kernel_namespace = provisioner_info["kernel_ns"]
        self.delete_kernel_namespace = provisioner_info["delete_ns"]

    @overrides
    def get_initial_states(self) -> Set[str]:
        return {"Pending", "Running"}

    @overrides
    async def get_container_status(self, iteration: Optional[str]) -> str:
        # Locates the kernel pod using the kernel_id selector.  Note that we also include 'component=kernel'
        # in the selector so that executor pods (when Spark is in use) are not considered.
        # If the phase indicates Running, the pod's IP is used for the assigned_ip.
        pod_status = None
        kernel_label_selector = f"kernel_id={self.kernel_id},component=kernel"
        ret = client.CoreV1Api().list_namespaced_pod(
            namespace=self.kernel_namespace, label_selector=kernel_label_selector
        )
        if ret and ret.items:
            pod_info = ret.items[0]
            self.container_name = pod_info.metadata.name
            if pod_info.status:
                pod_status = pod_info.status.phase
                if pod_status == "Running" and not self.assigned_host:
                    # Pod is running, capture IP
                    self.assigned_ip = pod_info.status.pod_ip
                    self.assigned_host = self.container_name
                    self.assigned_node_ip = pod_info.status.host_ip

        if iteration:  # only log if iteration is not None (otherwise poll() is too noisy)
            self.log.debug(
                f"{iteration}: Waiting to connect to k8s pod in namespace "
                f"'{self.kernel_namespace}'. Name: '{self.container_name}', "
                f"Status: '{pod_status}', Pod IP: '{self.assigned_ip}', "
                f"KernelID: '{self.kernel_id}'"
            )

        return pod_status

    @overrides
    async def terminate_container_resources(self, restart: bool = False) -> Optional[bool]:
        # Kubernetes objects don't go away on their own - so we need to tear down the namespace
        # or pod associated with the kernel.  If we created the namespace, and we're not in the
        # process of restarting the kernel, then that's our target, else just delete the pod.

        result = False
        body = client.V1DeleteOptions(grace_period_seconds=0, propagation_policy="Background")

        # If this termination is due to a restart, record that fact, so we can tolerate
        # things like the existence of pre-existing namespaces (when auto-creation is
        # in play), etc.
        self.restarting = restart

        # Delete the pod then, if applicable, the namespace
        try:
            object_name = "pod"
            status = None
            termination_stati = ["Succeeded", "Failed", "Terminating"]

            # Deleting a Pod will return a v1.Pod if found and its status will be a PodStatus containing
            # a phase string property
            # https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.21/#podstatus-v1-core
            v1_pod = client.CoreV1Api().delete_namespaced_pod(
                namespace=self.kernel_namespace, body=body, name=self.container_name
            )
            if v1_pod and v1_pod.status:
                status = v1_pod.status.phase

            if status in termination_stati:
                result = True

            if not result:
                # If the status indicates the pod is not terminated, capture its current status.
                # If None, update the result to True, else issue warning that it is not YET deleted
                # since we still have the hard termination sequence to occur.
                cur_status = await self.get_container_status(None)
                if cur_status is None:
                    result = True
                else:
                    self.log.warning(
                        f"Pod {self.kernel_namespace}.{self.container_name} is not yet deleted.  "
                        f"Current status is '{cur_status}'."
                    )

            if self.delete_kernel_namespace and not self.restarting:
                object_name = "namespace"
                # Status is a return value for calls that don't return other objects.
                # https://kubernetes.io/docs/reference/generated/kubernetes-api/v1.21/#status-v1-meta
                v1_status = client.CoreV1Api().delete_namespace(
                    name=self.kernel_namespace, body=body
                )
                if v1_status:
                    status = v1_status.status

                if status:
                    if any(s in status for s in termination_stati):
                        result = True

                if not result:
                    self.log.warning(
                        f"Namespace {self.kernel_namespace} is not yet deleted.  "
                        f"Current status is '{status}'."
                    )
        except Exception as err:
            if isinstance(err, client.rest.ApiException) and err.status == 404:
                result = True  # okay if it's not found
            else:
                self.log.warning(f"Error occurred deleting {object_name}: {err}")

        if result:
            self.log.debug(
                f"KubernetesProvisioner.terminate_container_resources, pod: {self.kernel_namespace}."
                f"{self.container_name}, kernel ID: {self.kernel_id} has been terminated."
            )
            self.container_name = None
            result = None  # maintain jupyter contract
        else:
            self.log.warning(
                f"KubernetesProvisioner.terminate_container_resources, pod: {self.kernel_namespace}."
                f"{self.container_name}, kernel ID: {self.kernel_id} has not been terminated."
            )

        # Check if there's a kernel pod template file for this kernel and silently delete it.
        kpt_file = f"{kpt_dir}/kpt_{self.kernel_id}"
        try:
            os.remove(kpt_file)
        except OSError:
            pass

        return result

    def _determine_kernel_pod_name(self, **kwargs):
        pod_name = kwargs["env"].get("KERNEL_POD_NAME")
        if pod_name is None:
            pod_name = f"{self.kernel_username}-{self.kernel_id}"

        # Rewrite pod_name to be compatible with DNS name convention
        # And put back into env since kernel needs this
        pod_name = re.sub("[^0-9a-z]+", "-", pod_name.lower())
        while pod_name.startswith("-"):
            pod_name = pod_name[1:]
        while pod_name.endswith("-"):
            pod_name = pod_name[:-1]
        kwargs["env"]["KERNEL_POD_NAME"] = pod_name

        return pod_name

    def _determine_kernel_namespace(self, **kwargs):

        # Since we need the service account name regardless of whether we're creating the namespace or not,
        # get it now.
        service_account_name = KubernetesProvisioner._determine_kernel_service_account_name(
            **kwargs
        )

        # If KERNEL_NAMESPACE was provided, then we assume it already exists.  If not provided, then we'll
        # create the namespace and record that we'll want to delete it as well.
        namespace = kwargs["env"].get("KERNEL_NAMESPACE")
        if namespace is None:
            # check if share gateway namespace is configured...
            if shared_namespace:  # if so, set to RP namespace
                namespace = k8s_provisioner_namespace
                self.log.warning(
                    f"Shared namespace has been configured.  All kernels will reside "
                    f"in the namespace: {namespace}"
                )
            else:
                namespace = self._create_kernel_namespace(service_account_name)
            kwargs["env"]["KERNEL_NAMESPACE"] = namespace  # record in env since kernel needs this
        else:
            self.log.info(f"KERNEL_NAMESPACE provided by client: {namespace}")

        return namespace

    @staticmethod
    def _determine_kernel_service_account_name(**kwargs):
        # Check if an account name was provided.  If not, set to the default name (which can be set
        # from the EG env as well).  Finally, ensure the env value is set.
        service_account_name = kwargs["env"].get(
            "KERNEL_SERVICE_ACCOUNT_NAME", default_kernel_service_account_name
        )
        kwargs["env"]["KERNEL_SERVICE_ACCOUNT_NAME"] = service_account_name
        return service_account_name

    def _create_kernel_namespace(self, service_account_name):
        # Creates the namespace for the kernel based on the kernel username and kernel id.  Since we're creating
        # the namespace, we'll also note that it should be deleted as well.  In addition, the kernel pod may need
        # to list/create other pods (true for spark-on-k8s), so we'll also create a RoleBinding associated with
        # the namespace's default ServiceAccount.  Since this is always done when creating a namespace, we can
        # delete the RoleBinding when deleting the namespace (no need to record that via another member variable).

        namespace = self.kernel_pod_name

        # create the namespace ...
        labels = {"app": app_name, "component": "kernel", "kernel_id": self.kernel_id}
        namespace_metadata = client.V1ObjectMeta(name=namespace, labels=labels)
        body = client.V1Namespace(metadata=namespace_metadata)

        # create the namespace
        try:
            client.CoreV1Api().create_namespace(body=body)
            self.delete_kernel_namespace = True
            self.log.info(f"Created kernel namespace: {namespace}")

            # Now create a RoleBinding for this namespace for the default ServiceAccount.  We'll reference
            # the ClusterRole, but that will only be applied for this namespace.  This prevents the need for
            # creating a role each time.
            self._create_role_binding(namespace, service_account_name)
        except Exception as err:
            # Tolerate pre-existing namespace if we're in the process of restarting
            if isinstance(err, ApiException) and err.status == 409 and self.restarting:
                self.restarting = False
                self.delete_kernel_namespace = True  # still mark for delete
                self.log.info(f"Re-using kernel namespace: {namespace}")
            else:
                if self.delete_kernel_namespace:
                    reason = (
                        f"Error occurred creating role binding for namespace '{namespace}': {err}"
                    )
                    # delete the namespace since we'll be using the EG namespace...
                    body = client.V1DeleteOptions(
                        grace_period_seconds=0, propagation_policy="Background"
                    )
                    client.CoreV1Api().delete_namespace(name=namespace, body=body)
                    self.log.warning(f"Deleted kernel namespace: {namespace}")
                else:
                    reason = f"Error occurred creating namespace '{namespace}': {err}"
                self.log_and_raise(RuntimeError(reason), chained=err)

        return namespace

    def _create_role_binding(self, namespace, service_account_name):
        # Creates RoleBinding instance for the given namespace.  The role used will be the ClusterRole named by
        # EG_KERNEL_CLUSTER_ROLE.
        # Note that roles referenced in RoleBindings are scoped to the namespace so re-using the cluster role prevents
        # the need for creating a new role with each kernel.
        # The ClusterRole will be bound to the kernel service user identified by KERNEL_SERVICE_ACCOUNT_NAME then
        # EG_DEFAULT_KERNEL_SERVICE_ACCOUNT_NAME, respectively.
        # We will not use a try/except clause here since _create_kernel_namespace will handle exceptions.

        role_binding_name = kernel_cluster_role  # use same name for binding as cluster role
        labels = {"app": app_name, "component": "kernel", "kernel_id": self.kernel_id}
        binding_metadata = client.V1ObjectMeta(name=role_binding_name, labels=labels)
        binding_role_ref = client.V1RoleRef(
            api_group="", kind="ClusterRole", name=kernel_cluster_role
        )
        binding_subjects = client.V1Subject(
            api_group="",
            kind="ServiceAccount",
            name=service_account_name,
            namespace=namespace,
        )

        body = client.V1RoleBinding(
            kind="RoleBinding",
            metadata=binding_metadata,
            role_ref=binding_role_ref,
            subjects=[binding_subjects],
        )

        client.RbacAuthorizationV1Api().create_namespaced_role_binding(
            namespace=namespace, body=body
        )
        self.log.info(
            f"Created kernel role-binding '{role_binding_name}' in namespace: {namespace} "
            f"for service account: {service_account_name}"
        )
