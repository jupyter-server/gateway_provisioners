"""A spark operator provisioner."""
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from .crd import CustomResourceProvisioner


class SparkOperatorProvisioner(CustomResourceProvisioner):
    """Spark operator provisioner."""

    # Identifies the kind of object being managed by this provisioner.
    # For these values we will prefer the values found in the 'kind' field
    # of the object's metadata.  This attribute is strictly used to provide
    # context to log messages.
    object_kind = "SparkApplication"

    def __init__(self, **kwargs):
        """Initialize the provisioner."""
        super().__init__(**kwargs)
        self.group = "sparkoperator.k8s.io"
        self.version = "v1beta2"
        self.plural = "sparkapplications"
