# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import os
import shutil
from string import Template
from typing import Any

from jupyter_core.application import JupyterApp
from overrides import overrides
from traitlets import Bool, List, TraitError, Unicode, validate

from .._version import __version__
from .base_app import (
    PYTHON,
    SCALA,
    SUPPORTED_LANGUAGES,
    BaseApp,
    R,
    kernel_launchers_dir,
)

LANG_DIR_NAMES = {PYTHON: "python", SCALA: "scala", R: "R"}
BOOTSTRAP_FILE_NAME = "bootstrap-kernel.sh"
# Note that BOOTSTRAP_DIR is not configurable due to its reference buries in the
# sparkoperator.k8s.io/v1beta2.yaml.j2 template used by the Spark Operator.  We can
# revisit how to make this configurable later.
BOOTSTRAP_DIR = "/usr/local/bin"


class ImageBootstrapInstaller(BaseApp):
    """CLI for extension management."""

    name = "jupyter-image-bootstrap"
    description = (
        "Installs the bootstrap script and kernel launchers for use within a kernel "
        "image used by Remote Provisioners."
    )
    # Note that the left justification of the second example is necessary to ensure proper
    # alignment with the first example during --help output.
    examples = """
    jupyter-image-bootstrap install --languages=Python --languages=R

jupyter-image-bootstrap install --languages=Python --languages=Scala
    """

    languages = List(
        Unicode(),
        ["Python"],
        config=True,
        help="""The languages corresponding to the kernel-launchers to install into the kernel image.
    All values must be one of 'Python', 'R', or 'Scala'.""",
    )

    @validate("languages")
    def _languages_validate(self, proposal: dict[str, Any]) -> List:
        value = proposal["value"]
        try:
            for lang in value:
                assert lang.lower() in SUPPORTED_LANGUAGES
        except AssertionError as ae:
            err_msg = (
                f"Invalid languages value {value}, at least one of which is "
                f"not in {SUPPORTED_LANGUAGES} (case-insensitive)"
            )
            raise TraitError(err_msg) from ae
        return value

    launchers_only = Bool(
        False, config=True, help="Only install kernel launchers, no bootstrap script."
    )

    aliases = {
        "languages": "ImageBootstrapInstaller.languages",
    }
    aliases.update(BaseApp.aliases)

    flags = {
        "launchers-only": (
            {"ImageBootstrapInstaller": {"launchers_only": True}},
            "Only install kernel launchers, no bootstrap script.",
        ),
    }
    flags.update(BaseApp.flags)

    kernel_spec_install = False  # Set to false when bootstrap installation occurs

    @overrides
    def detect_missing_extras(self):
        for lang in self.languages:
            if lang.lower() == SCALA:
                self._detect_missing_toree_jar()
            elif lang.lower() == R:
                self._detect_missing_rscript()

    @overrides
    def install_files(self):
        """Sets up the bootstrap-kernel.sh and corresponding kernel-launchers for use in kernel images"""

        parent_dir = os.path.join(BOOTSTRAP_DIR, "kernel-launchers")
        for lang in self.languages:
            lang_dir_name = LANG_DIR_NAMES.get(lang.lower())
            if not lang_dir_name:
                continue
            target_dir = os.path.join(parent_dir, lang_dir_name)
            self._copy_launcher_files(lang_dir_name, target_dir)
            if lang_dir_name == SCALA and not self.toree_jar_path:
                # If we're installing a scala kernel launcher and don't have the toree jar file, issue
                # a warning indicating that the scala kernel needs that file in its kernel-launcher
                # directory hierarchy.
                kspec_toree_jar_location = os.path.join(target_dir, "lib")
                self.log.warning(
                    "The Apache Toree kernel is either not installed or it's jar file cannot be determined. "
                    f"Please ensure that the Toree jar file is placed into '{kspec_toree_jar_location}' "
                    f"prior to using the kernel image for scala."
                )
        if self.languages:
            self.log.info(
                f"Kernel-launcher files have been copied to {parent_dir} "
                f"for the following languages: {self.languages}."
            )

        if not self.launchers_only:
            bootstrap_file = os.path.join(kernel_launchers_dir, "bootstrap", BOOTSTRAP_FILE_NAME)
            target_bootstrap_file = os.path.join(BOOTSTRAP_DIR, BOOTSTRAP_FILE_NAME)
            shutil.copyfile(bootstrap_file, target_bootstrap_file)
            self._finalize_bootstrap(target_bootstrap_file)
            self.log.info(f"{BOOTSTRAP_FILE_NAME} has been copied to {BOOTSTRAP_DIR}.")
            self.log.info(
                f"The CMD entry in the Dockerfile should be updated to: CMD {target_bootstrap_file}"
            )

    @staticmethod
    def _finalize_bootstrap(bootstrap_file: str):
        subs = {"install_dir": BOOTSTRAP_DIR}
        bootstrap_str = ""
        with open(bootstrap_file) as f:
            for line in f:
                bootstrap_str = bootstrap_str + line
            f.close()
        post_subs = Template(bootstrap_str).safe_substitute(subs)
        with open(bootstrap_file, "w+") as f:
            f.write(post_subs)


class ImageBootstrapApp(JupyterApp):
    """Application responsible for driving the creation of Kubernetes-based kernel specifications."""

    version = __version__
    name = "jupyter image-bootstrap"
    description = """Application used to bootstrap kernel images with the appropriate
kernel launchers for use by Remote Provisioners."""
    subcommands = {
        "install": (
            ImageBootstrapInstaller,
            ImageBootstrapInstaller.description.splitlines()[0],
        ),
    }
    aliases = {}
    flags = {}

    def start(self):
        super().start()

        if self.subapp is None:
            print(f"No subcommand specified. Must specify one of: {list(self.subcommands)}")
            print()
            self.print_description()
            self.print_subcommands()
            self.exit(1)


if __name__ == "__main__":
    ImageBootstrapInstaller.launch_instance()
