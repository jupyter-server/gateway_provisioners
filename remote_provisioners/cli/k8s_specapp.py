# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import os

from traitlets import Bool, Unicode, default
from traitlets.config.application import Application

from .._version import __version__
from .base_specapp import DEFAULT_LANGUAGE, PYTHON, SCALA, BaseSpecApp, R

DEFAULT_KERNEL_NAMES = {PYTHON: "k8s_python", SCALA: "k8s_scala", R: "k8s_r"}
KERNEL_SPEC_TEMPLATE_NAMES = {
    PYTHON: "container_python",
    SCALA: "container_scala",
    R: "container_r",
}
DEFAULT_DISPLAY_NAMES = {PYTHON: "Kubernetes Python", SCALA: "Kubernetes Scala", R: "Kubernetes R"}
DEFAULT_IMAGE_NAMES = {PYTHON: "elyra/kernel-py", SCALA: "elyra/kernel-scala", R: "elyra/kernel-r"}
DEFAULT_SPARK_IMAGE_NAMES = {
    PYTHON: "elyra/kernel-spark-py",
    SCALA: "elyra/kernel-scala",
    R: "elyra/kernel-spark-r",
}

SPARK_SUFFIX = "_spark"
SPARK_DISPLAY_NAME_SUFFIX = " (with Spark)"

PROVISIONER_NAME = "kubernetes-provisioner"
LAUNCHER_NAME = "launch_kubernetes.py"


class K8sSpecApp(BaseSpecApp):
    """CLI for extension management."""

    name = "jupyter-k8s-spec"
    description = "Creates a Jupyter kernel specification for use within a Kubernetes cluster."
    # Note that the left justification of the second example is necessary to ensure proper
    # alignment with the first example during --help output.
    examples = """
    jupyter-k8s-spec install --language=R --kernel-name=r_k8s --image-name=foo/my_r_kernel_image:v4_0

jupyter-k8s-spec install --language=Scala --spark --kernel-name=scala_k8s_spark
    --display-name='Scala on Kubernetes with Spark'
    """

    @default("kernel_name")
    def kernel_name_default(self) -> str:
        return DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]

    @default("display_name")
    def display_name_default(self) -> str:
        return DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]

    # Image name
    image_name_env = "RP_IMAGE_NAME"
    image_name = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""The kernel image to use for this kernel specification. If this specification is
enabled for Spark usage, this image will be the driver image. (RP_IMAGE_NAME env var)""",
    )

    @default("image_name")
    def image_name_default(self):
        return os.getenv(self.image_name_env)

    executor_image_name_env = "RP_EXECUTOR_IMAGE_NAME"
    executor_image_name = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""The executor image to use for this kernel specification.  Only applies to
Spark-enabled kernel specifications.  (RP_EXECUTOR_IMAGE_NAME env var)""",
    )

    @default("executor_image_name")
    def executor_image_name_default(self):
        return os.getenv(self.executor_image_name_env)

    # Flags
    tensorflow = Bool(False, config=True, help="""Install kernel for use with Tensorflow.""")

    provisioner_name = Unicode(PROVISIONER_NAME, config=False)
    launcher_name = Unicode(LAUNCHER_NAME, config=False)

    aliases = {
        "image-name": "K8sSpecApp.image_name",
        "executor-image-name": "K8sSpecApp.executor_image_name",
    }
    aliases.update(BaseSpecApp.super_aliases)

    flags = {}
    flags.update(BaseSpecApp.super_flags)

    def detect_missing_extras(self):
        """Issues a warning message whenever an "extra" library is detected as missing."""
        try:
            import jinja2  # noqa: F401
            import kubernetes  # noqa: F401
        except ImportError:
            self.log.warning(
                "At least one of the extra packages 'kubernetes' or 'jinja2' are not installed in "
                "this environment and are required.  Ensure that remote_provisioners is installed "
                "by specifying the extra 'k8s' (e.g., pip install 'remote_provisioners[k8s]')."
            )

    def validate_parameters(self):
        """Validate input parameters and prepare for their injection into templated files."""
        super().validate_parameters()

        self.language = self.language.lower()
        self.launcher_dir_name = "kubernetes"
        self.resource_dir_name = self.language

        if self.spark is True:
            # if kernel and display names are still defaulted, silently convert to lang default and append spark suffix
            if self.kernel_name == DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]:
                self.kernel_name = DEFAULT_KERNEL_NAMES[self.language] + SPARK_SUFFIX
            if self.display_name == DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]:
                self.display_name = DEFAULT_DISPLAY_NAMES[self.language] + SPARK_DISPLAY_NAME_SUFFIX

            self.kernel_spec_dir_name = DEFAULT_KERNEL_NAMES[self.language] + SPARK_SUFFIX

            if self.image_name is None:
                self.image_name = f"{DEFAULT_SPARK_IMAGE_NAMES[self.language]}:{self._get_tag()}"
            if self.executor_image_name is None:
                self.executor_image_name = self.image_name
        else:
            # if kernel and display names are still defaulted, silently change to language defaults
            if self.kernel_name == DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]:
                self.kernel_name = DEFAULT_KERNEL_NAMES[self.language]
            if self.display_name == DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]:
                self.display_name = DEFAULT_DISPLAY_NAMES[self.language]

            self.kernel_spec_dir_name = KERNEL_SPEC_TEMPLATE_NAMES[self.language]

            if self.image_name is None:
                self.image_name = f"{DEFAULT_IMAGE_NAMES[self.language]}:{self._get_tag()}"

            self.spark_init_mode = "none"
            if len(self.extra_spark_opts) > 0:
                self.log.warning(
                    "--extra_spark_opts will be ignored since --spark has not been specified."
                )
                self.extra_spark_opts = ""

        # sanitize kernel_name
        self.kernel_name = self.kernel_name.replace(" ", "_")

    def get_substitutions(self, install_dir) -> dict:
        """Gather substitution strings to inject into the templated files."""
        substitutions = super().get_substitutions(install_dir)
        substitutions["image_name"] = self.image_name
        substitutions["executor_image_name"] = self.executor_image_name
        substitutions["provisioner_name"] = self.provisioner_name
        substitutions["launcher_name"] = self.launcher_name
        return substitutions


class K8sProvisionerApp(Application):
    """Application responsible for driving the creation of Kubernetes-based kernel specifications."""

    version = __version__
    name = "jupyter k8s-spec"
    description = """Application used to create kernel specifications for use on Kubernetes clusters
    via the KubernetesProvisioner kernel provisioner."""
    subcommands = dict(
        {
            "install": (K8sSpecApp, K8sSpecApp.description.splitlines()[0]),
        }
    )
    aliases = {}
    flags = {}

    def start(self):
        if self.subapp is None:
            print(f"No subcommand specified. Must specify one of: {list(self.subcommands)}")
            print()
            self.print_description()
            self.print_subcommands()
            self.exit(1)
        else:
            return self.subapp.start()


if __name__ == "__main__":
    K8sProvisionerApp.launch_instance()
