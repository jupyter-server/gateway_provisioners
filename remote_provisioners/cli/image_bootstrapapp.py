# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import os
import shutil
from string import Template
from typing import Any

from overrides import overrides
from traitlets import List, TraitError, Unicode, validate
from traitlets.config.application import Application

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
    jupyter-image-bootstrap install --languages=Python --languages=R --bootstrap-dir=/usr/local/share

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
    def languages_validate(self, proposal: dict[str, Any]) -> List:
        value = proposal["value"]
        try:
            for lang in value:
                assert lang.lower() in SUPPORTED_LANGUAGES
        except AssertionError:
            raise TraitError(
                f"Invalid languages value {value}, at least one of which is "
                f"not in {SUPPORTED_LANGUAGES} (case-insensitive)"
            )
        return value

    bootstrap_dir = Unicode(
        "/usr/local/bin",
        config=True,
        help="Specifies the absolute directory within the kernel-image in which "
        f"{BOOTSTRAP_FILE_NAME} should be installed.",
    )

    @validate("bootstrap_dir")
    def bootstrap_dir_validate(self, proposal: dict[str, Any]) -> str:
        value = proposal["value"]
        try:
            assert os.path.isabs(value)
        except AssertionError:
            raise TraitError(f"Invalid bootstrap_dir value!  '{value}' must be an absolute path.")
        return value

    aliases = {
        "languages": "ImageBootstrapInstaller.languages",
        "bootstrap-dir": "ImageBootstrapInstaller.bootstrap_dir",
    }
    aliases.update(BaseApp.aliases)

    flags = {}
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

        parent_dir = os.path.join(self.bootstrap_dir, "kernel-launchers")
        for lang in self.languages:
            lang_dir_name = LANG_DIR_NAMES.get(lang.lower())
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

        bootstrap_file = os.path.join(kernel_launchers_dir, "bootstrap", BOOTSTRAP_FILE_NAME)
        target_bootstrap_file = os.path.join(self.bootstrap_dir, BOOTSTRAP_FILE_NAME)
        shutil.copyfile(bootstrap_file, target_bootstrap_file)
        self._finalize_bootstrap(target_bootstrap_file)
        self.log.info(
            f"{BOOTSTRAP_FILE_NAME} and kernel-launcher files have been copied to {self.bootstrap_dir} "
            f"and {parent_dir} for the following languages: {self.languages}."
        )
        self.log.info(
            f"The CMD entry in the Dockerfile should be updated to: CMD {target_bootstrap_file}"
        )

    def _finalize_bootstrap(self, bootstrap_file: str):
        subs = {"install_dir": self.bootstrap_dir}
        bootstrap_str = ""
        with open(bootstrap_file) as f:
            for line in f:
                bootstrap_str = bootstrap_str + line
            f.close()
        post_subs = Template(bootstrap_str).safe_substitute(subs)
        with open(bootstrap_file, "w+") as f:
            f.write(post_subs)


class ImageBootstrapApp(Application):
    """Application responsible for driving the creation of Kubernetes-based kernel specifications."""

    version = __version__
    name = "jupyter image-bootstrap"
    description = """Application used to bootstrap kernel images with the appropriate
kernel launchers for use by Remote Provisioners."""
    subcommands = dict(
        {
            "install": (
                ImageBootstrapInstaller,
                ImageBootstrapInstaller.description.splitlines()[0],
            ),
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
    ImageBootstrapInstaller.launch_instance()
