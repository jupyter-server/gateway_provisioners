# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Code related to managing kernels running in Kubernetes clusters."""

import os
import logging
import re

import urllib3

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Any, Dict, Optional, Set

from .container import ContainerProvisioner

urllib3.disable_warnings()

# Default logging level of kubernetes produces too much noise - raise to warning only.
logging.getLogger('kubernetes').setLevel(os.environ.get('EG_KUBERNETES_LOG_LEVEL', logging.WARNING))

enterprise_gateway_namespace = os.environ.get('EG_NAMESPACE', 'default')
default_kernel_service_account_name = os.environ.get('EG_DEFAULT_KERNEL_SERVICE_ACCOUNT_NAME', 'default')
kernel_cluster_role = os.environ.get('EG_KERNEL_CLUSTER_ROLE', 'cluster-admin')

# TODO: The default for this value should probably flip for single-user/Notebook scenarios (True) vs.
# multi-tenant/Gateway scenarios (False).  The app config will be available from `kernel_manager.app_config`
# so we should be able to move this into constructor (or after) and infer from that information.
# Since provisioners are a single-user scenario (not going through EG), use a shared namespace.
shared_namespace = bool(os.environ.get('RP_SHARED_NAMESPACE', 'True').lower() == 'true')

if bool(os.environ.get('RP_USE_INCLUSTER_CONFIG', 'True').lower() == 'true'):
    config.load_incluster_config()
else:
    config.load_kube_config()


class KubernetesProvisioner(ContainerProvisioner):
    """Kernel lifecycle management for Kubernetes kernels."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.kernel_pod_name = None
        self.kernel_namespace = None
        self.delete_kernel_namespace = False

    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        """Prepares a kernel's launch within a Kubernetes environment."""
        # Set env before superclass call so we see these in the debug output

        # Kubernetes relies on many internal env variables.  Since we're running in a k8s pod, we will
        # transfer its env to each launched kernel.
        kwargs['env'] = dict(os.environ, **kwargs.get('env', {}))
        kwargs = await super().pre_launch(**kwargs)
        # These must follow call to super() so that kernel_username is established
        self.kernel_pod_name = self._determine_kernel_pod_name(**kwargs)
        self.kernel_namespace = self._determine_kernel_namespace(**kwargs)  # will create namespace if not provided
        return kwargs

    def get_initial_states(self) -> Set[str]:
        """Return list of states indicating container is starting (includes running)."""
        return {'Pending', 'Running'}

    async def get_container_status(self, iteration: Optional[str]) -> str:
        """Return current container state."""
        # Locates the kernel pod using the kernel_id selector.  If the phase indicates Running, the pod's IP
        # is used for the assigned_ip.
        pod_status = None
        ret = client.CoreV1Api().list_namespaced_pod(namespace=self.kernel_namespace,
                                                     label_selector="kernel_id=" + self.kernel_id)
        if ret and ret.items:
            pod_info = ret.items[0]
            self.container_name = pod_info.metadata.name
            if pod_info.status:
                pod_status = pod_info.status.phase
                if pod_status == 'Running' and self.assigned_host == '':
                    # Pod is running, capture IP
                    self.assigned_ip = pod_info.status.pod_ip
                    self.assigned_host = self.container_name
                    self.assigned_node_ip = pod_info.status.host_ip

        if iteration:  # only log if iteration is not None (otherwise poll() is too noisy)
            self.log.debug(f"{iteration}: Waiting to connect to k8s pod in namespace "
                           f"'{self.kernel_namespace}'. Name: '{self.container_name}', "
                           f"Status: '{pod_status}', Pod IP: '{self.assigned_ip}', "
                           f"KernelID: '{self.kernel_id}'")

        return pod_status

    async def terminate_container_resources(self, restart: bool = False) -> None:
        """Terminate any artifacts created on behalf of the container's lifetime."""
        # Kubernetes objects don't go away on their own - so we need to tear down the namespace
        # or pod associated with the kernel.  If we created the namespace and we're not in the
        # the process of restarting the kernel, then that's our target, else just delete the pod.

        result = False
        body = client.V1DeleteOptions(grace_period_seconds=0, propagation_policy='Background')

        # Delete the namespace or pod...
        object_name: str = 'pod'  # default to pod
        try:
            # What gets returned from this call is a 'V1Status'.  It looks a bit like JSON but appears to be
            # intentionally obfuscated.  Attempts to load the status field fail due to malformed json.  As a
            # result, we'll rely on the fact that the api will raise exceptions on failure and we'll tolerate
            # 404 (for this case).

            if self.delete_kernel_namespace and not restart:
                object_name = 'namespace'
                client.CoreV1Api().delete_namespace(name=self.kernel_namespace, body=body)
            else:
                client.CoreV1Api().delete_namespaced_pod(namespace=self.kernel_namespace,
                                                         body=body, name=self.container_name)
            result = True
        except Exception as err:
            if isinstance(err, ApiException) and err.status == 404:
                result = True  # okay if its not found
            else:
                self.log.warning(f"Error occurred deleting {object_name}: {err}")

        if result:
            self.log.debug(f"KubernetesProvisioner.terminate_container_resources, "
                           f"pod: {self.kernel_namespace}.{self.container_name}, "
                           f"kernel ID: {self.kernel_id} has been terminated.")
            self.container_name = None
            result = None  # maintain jupyter contract
        else:
            self.log.warning(f"KubernetesProvisioner.terminate_container_resources, "
                             f"pod: {self.kernel_namespace}.{self.container_name}, "
                             f"kernel ID: {self.kernel_id} has not been terminated.")
        return result

    def _determine_kernel_pod_name(self, **kwargs):
        pod_name = kwargs['env'].get('KERNEL_POD_NAME')
        if pod_name is None:
            pod_name = self.kernel_username + '-' + self.kernel_id

        # Rewrite pod_name to be compatible with DNS name convention
        # And put back into env since kernel needs this
        pod_name = re.sub('[^0-9a-z]+', '-', pod_name.lower())
        while pod_name.startswith('-'):
            pod_name = pod_name[1:]
        while pod_name.endswith('-'):
            pod_name = pod_name[:-1]
        kwargs['env']['KERNEL_POD_NAME'] = pod_name

        return pod_name

    def _determine_kernel_namespace(self, **kwargs):

        # Since we need the service account name regardless of whether we're creating the namespace or not,
        # get it now.
        service_account_name = KubernetesProvisioner._determine_kernel_service_account_name(**kwargs)

        # If KERNEL_NAMESPACE was provided, then we assume it already exists.  If not provided, then we'll
        # create the namespace and record that we'll want to delete it as well.
        namespace = kwargs['env'].get('KERNEL_NAMESPACE')
        if namespace is None:
            # check if share gateway namespace is configured...
            if shared_namespace:  # if so, set to EG namespace
                namespace = enterprise_gateway_namespace
                self.log.warning("Shared namespace has been configured.  All kernels will reside in EG namespace: {}".
                                 format(namespace))
            else:
                namespace = self._create_kernel_namespace(service_account_name)
            kwargs['env']['KERNEL_NAMESPACE'] = namespace  # record in env since kernel needs this
        else:
            self.log.info("KERNEL_NAMESPACE provided by client: {}".format(namespace))

        return namespace

    @staticmethod
    def _determine_kernel_service_account_name(**kwargs):
        # Check if an account name was provided.  If not, set to the default name (which can be set
        # from the EG env as well).  Finally, ensure the env value is set.
        service_account_name = kwargs['env'].get('KERNEL_SERVICE_ACCOUNT_NAME', default_kernel_service_account_name)
        kwargs['env']['KERNEL_SERVICE_ACCOUNT_NAME'] = service_account_name
        return service_account_name

    def _create_kernel_namespace(self, service_account_name):
        # Creates the namespace for the kernel based on the kernel username and kernel id.  Since we're creating
        # the namespace, we'll also note that it should be deleted as well.  In addition, the kernel pod may need
        # to list/create other pods (true for spark-on-k8s), so we'll also create a RoleBinding associated with
        # the namespace's default ServiceAccount.  Since this is always done when creating a namespace, we can
        # delete the RoleBinding when deleting the namespace (no need to record that via another member variable).

        namespace = self.kernel_pod_name

        # create the namespace ...
        labels = {'app': 'enterprise-gateway', 'component': 'kernel', 'kernel_id': self.kernel_id}
        namespace_metadata = client.V1ObjectMeta(name=namespace, labels=labels)
        body = client.V1Namespace(metadata=namespace_metadata)

        # create the namespace
        try:
            client.CoreV1Api().create_namespace(body=body)
            self.delete_kernel_namespace = True
            self.log.info("Created kernel namespace: {}".format(namespace))

            # Now create a RoleBinding for this namespace for the default ServiceAccount.  We'll reference
            # the ClusterRole, but that will only be applied for this namespace.  This prevents the need for
            # creating a role each time.
            self._create_role_binding(namespace, service_account_name)
        except Exception as err:
            # FIXME - self.parent is the kernel manager. We probably want a better means of determining
            # a launch is for the purpose of a restart.
            if isinstance(err, ApiException) and err.status == 409 and self.parent.restarting:
                self.delete_kernel_namespace = True  # okay if ns already exists and restarting, still mark for delete
                self.log.info(f"Re-using kernel namespace: {namespace}")
            else:
                if self.delete_kernel_namespace:
                    reason = f"Error occurred creating role binding for namespace '{namespace}': {err}"
                    # delete the namespace since we'll be using the EG namespace...
                    body = client.V1DeleteOptions(grace_period_seconds=0, propagation_policy='Background')
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
        labels = {'app': 'enterprise-gateway', 'component': 'kernel', 'kernel_id': self.kernel_id}
        binding_metadata = client.V1ObjectMeta(name=role_binding_name, labels=labels)
        binding_role_ref = client.V1RoleRef(api_group='', kind='ClusterRole', name=kernel_cluster_role)
        binding_subjects = client.V1Subject(api_group='', kind='ServiceAccount', name=service_account_name,
                                            namespace=namespace)

        body = client.V1RoleBinding(kind='RoleBinding', metadata=binding_metadata, role_ref=binding_role_ref,
                                    subjects=[binding_subjects])

        client.RbacAuthorizationV1Api().create_namespaced_role_binding(namespace=namespace, body=body)
        self.log.info(f"Created kernel role-binding '{role_binding_name}' in namespace: {namespace} "
                      f"for service account: {service_account_name}")

    async def get_provisioner_info(self) -> Dict:
        """Captures the base information necessary for kernel persistence relative to kubernetes."""
        provisioner_info = await super().get_provisioner_info()
        provisioner_info.update({'kernel_ns': self.kernel_namespace, 'delete_ns': self.delete_kernel_namespace})
        return provisioner_info

    async def load_provisioner_info(self, provisioner_info: Dict) -> None:
        """Loads the base information necessary for kernel persistence relative to kubernetes."""
        await super().load_provisioner_info(provisioner_info)
        self.kernel_namespace = provisioner_info['kernel_ns']
        self.delete_kernel_namespace = provisioner_info['delete_ns']
