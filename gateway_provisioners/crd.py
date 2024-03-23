"""Code related to managing kernels running based on k8s custom resource."""
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import logging
import re
from contextlib import suppress
from typing import Any, Dict, List, Optional, Set

from overrides import overrides

try:
    from kubernetes import client  # type:ignore[import-untyped]
except ImportError:
    logging.warning(
        "At least one of the extra packages 'kubernetes' or 'jinja2' are not installed in "
        "this environment and are required.  Ensure that gateway_provisioners is installed "
        "by specifying the extra 'k8s' (e.g., pip install 'gateway_provisioners[k8s]')."
    )
    raise

from .k8s import KubernetesProvisioner


class CustomResourceProvisioner(KubernetesProvisioner):
    """A custom resource provisioner."""

    # Identifies the kind of object being managed by this provisioner.
    # For these values we will prefer the values found in the 'kind' field
    # of the object's metadata.  This attribute is strictly used to provide
    # context to log messages.
    object_kind = "CustomResourceDefinition"

    def __init__(self, **kwargs):
        """Initialize the provisioner."""
        super().__init__(**kwargs)
        self.group = self.version = self.plural = None
        self.kernel_resource_name = None

    @overrides
    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        """Launch the process for a kernel."""
        kwargs = await super().pre_launch(**kwargs)
        self.kernel_resource_name = self._determine_kernel_pod_name(**kwargs)
        kwargs["env"]["KERNEL_RESOURCE_NAME"] = self.kernel_resource_name
        kwargs["env"]["KERNEL_CRD_GROUP"] = self.group
        kwargs["env"]["KERNEL_CRD_VERSION"] = self.version
        kwargs["env"]["KERNEL_CRD_PLURAL"] = self.plural
        return kwargs

    @overrides
    def get_container_status(self, iteration: Optional[str]) -> str:
        """Determines submitted CRD application status

        Submitting a new kernel application CRD will take a while to
        reach the running state and the submission can also fail due
        to malformation or other issues which will prevent the application
        pod to reach the desired running state.

        This function checks the CRD submission state and in case of
        success it then delegates to parent to check if the application
        pod is running.

        Returns
        -------
        Empty string if the container cannot be found otherwise.
        The pod application status in case of success on Spark Operator side
        Or the retrieved spark operator submission status in other cases (e.g. Failed)
        """

        application_state = ""

        with suppress(Exception):
            custom_resource = client.CustomObjectsApi().get_namespaced_custom_object(
                self.group,
                self.version,
                self.kernel_namespace,
                self.plural,
                self.kernel_resource_name,
            )

            if custom_resource:
                application_state = custom_resource["status"]["applicationState"]["state"].lower()

                if application_state in self.get_error_states():
                    exception_text = CustomResourceProvisioner._get_exception_text(
                        custom_resource["status"]["applicationState"]["errorMessage"]
                    )
                    error_message = (
                        f"CRD submission for kernel {self.kernel_id} failed: {exception_text}"
                    )
                    self.log.debug(error_message)
                elif application_state == "running" and not self.assigned_host:
                    application_state = super().get_container_status(iteration)

        # only log if iteration is not None (otherwise poll() is too noisy)
        # check for running state to avoid double logging with superclass
        if iteration and application_state != "running":
            self.log.debug(
                f"{iteration}: Waiting from CRD status from resource manager {self.object_kind.lower()} in "
                f"namespace '{self.kernel_namespace}'. Name: '{self.kernel_resource_name}', "
                f"Status: '{application_state}', KernelID: '{self.kernel_id}'"
            )

        return application_state

    @overrides
    def delete_managed_object(self, termination_stati: List[str]) -> bool:
        """Deletes the object managed by this provisioner

        A return value of True indicates the object is considered deleted,
        otherwise a False or None value is returned.

        Note: the caller is responsible for handling exceptions.
        """
        delete_status = client.CustomObjectsApi().delete_namespaced_custom_object(
            self.group,
            self.version,
            self.kernel_namespace,
            self.plural,
            self.kernel_resource_name,
            grace_period_seconds=0,
            propagation_policy="Background",
        )

        result = delete_status and delete_status.get("status", None) in termination_stati

        return result

    @overrides
    def get_initial_states(self) -> Set[str]:
        """Return list of states in lowercase indicating container is starting (includes running)."""
        return {"submitted", "pending", "running"}

    @staticmethod
    def _get_exception_text(error_message) -> str:
        match = re.search(r"Exception\s*:\s*(.*)", error_message, re.MULTILINE)

        if match:
            error_message = match.group(1)

        return error_message
