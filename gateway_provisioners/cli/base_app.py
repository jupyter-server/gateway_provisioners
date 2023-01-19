# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from glob import glob
from string import Template
from typing import Any

from jupyter_client.kernelspec import KernelSpec, KernelSpecManager
from jupyter_core.application import JupyterApp, base_aliases, base_flags
from overrides import overrides
from traitlets import Bool, Instance, TraitError, Unicode, default, validate

from .._version import __version__
from ..config_mixin import RemoteProvisionerConfigMixin

kernel_launchers_dir = os.path.join(os.path.dirname(__file__), "..", "kernel-launchers")
kernel_resources_dir = os.path.join(os.path.dirname(__file__), "..", "kernel-resources")
kernel_specs_dir = os.path.join(os.path.dirname(__file__), "..", "kernel-specs")

launcher_dirs = ["python", "r", "scala", "kubernetes", "docker", "operators"]
resource_dirs = ["python", "r", "scala"]

KERNEL_JSON = "kernel.json"
PYTHON = "python"
SCALA = "scala"
R = "r"
DASK = "dask"
DEFAULT_LANGUAGE = PYTHON
SUPPORTED_LANGUAGES = [PYTHON, SCALA, R]
DEFAULT_INIT_MODE = "lazy"
SPARK_INIT_MODES = [DEFAULT_INIT_MODE, "eager", "none"]
LANGUAGE_SUBSTITUTIONS = {PYTHON: PYTHON, R: "R", SCALA: SCALA}
DEFAULT_PYTHON_KERNEL_CLASS_NAME = "ipykernel.ipkernel.IPythonKernel"


class BaseApp(JupyterApp):
    """Base class containing parameters common to each provisioner."""

    kernel_spec_manager = Instance(KernelSpecManager)

    @default("kernel_spec_manager")
    def _kernel_spec_manager_default(self) -> KernelSpecManager:
        return KernelSpecManager()

    launcher_dir_name = Unicode()  # kernel-launchers directory name
    resource_dir_name = Unicode()  # kernel-resources directory name
    kernel_spec_dir_name = Unicode()  # kernel-specs directory name
    install_dir = Unicode()  # Final location for kernel spec
    toree_jar_path: str | None = None  # Location from which to copy the toree jar

    kernel_spec_install: bool = True  # Set to false when bootstrap installation occurs

    def start(self):
        """Drive the kernel specification creation."""
        super().start()

        self.validate_parameters()
        self.detect_missing_extras()
        self.install_files()

    def validate_parameters(self):
        """
        Validate input parameters and prepare for their injection into templated files.

        This method is overridden by subclasses which should call super().validate_parameters().
        """
        pass

    def detect_missing_extras(self):
        """
        Issues a warning message whenever an "extra" library is detected as missing.

        Note that "extra" can also mean things like Apache Toree is not installed when
        the language is Scala, or Rscript is not available when the language is R.
        """
        pass

    def _detect_missing_toree_jar(self):
        """
        Detects which aspects of Apache Toree are missing.

        If installed, then it determines the path to the toree jar file.  If the jar cannot be
        determined, appropriate warnings are issued.
        """
        self.toree_jar_path = None
        try:
            import toree
        except ImportError:
            self.log.warning(
                "The Apache Torre kernel package is not installed in this environment and is required "
                "for kernels of language 'Scala'.  Ensure that the 'apache-toree' package is installed "
                "(e.g., pip install 'apache-toree') then repeat this command to ensure the Apache Toree"
                "jar file is located in the kernel specification's lib directory prior to its use."
            )
        else:
            toree_version = toree.toreeapp.ToreeApp.version
            toree_lib_dir = os.path.join(os.path.dirname(toree.__file__), "lib")
            jars = glob(os.path.join(toree_lib_dir, f"toree-assembly-{toree_version}-*.jar"))
            if len(jars) < 1:
                self.log.warning(
                    "The Apache Torre kernel package is installed, but there doesn't appear to be a toree "
                    f"jar file located in the installation area: '{toree_lib_dir}' that matches the pattern "
                    f"'toree-assembly-{toree_version}-*.jar'.  This jar file is required for the proper "
                    "behavior of scala kernels."
                )
            elif len(jars) > 1:
                self.log.warning(
                    "The Apache Torre kernel package is installed, but there appears to be more than one "
                    f"toree-assembly jar file located in the installation area: '{toree_lib_dir}' that matches "
                    f"the pattern 'toree-assembly-{toree_version}-*.jar'.  You will need to ensure the appropriate "
                    "jar file is copied to the kernel specification's lib directory prior to its use."
                )
            else:
                self.toree_jar_path = jars[0]

    def _detect_missing_rscript(self):
        """Detects if Rscript is in current path and issues warning if not."""
        rscript_location = shutil.which("Rscript")
        if rscript_location is None:
            self.log.warning(
                "The executable 'Rscript' is not in the current PATH.  Please ensure that 'Rscript' "
                "is available prior to using this kernel specification."
            )

    def install_files(self):
        """Installs applicable files into the target location."""
        pass

    def _copy_launcher_files(self, launcher_dir_name: str, target_dir: str):
        """Copy the launcher files from the launcher directory to the destination staging directory."""

        src_dir = os.path.join(kernel_launchers_dir, launcher_dir_name)
        shutil.copytree(src=src_dir, dst=target_dir, dirs_exist_ok=True)

        # When the launcher_dir_name is either 'r' or 'python', we need to also copy the files
        # from the 'shared' launcher directory.
        if launcher_dir_name.lower() in [PYTHON, R]:
            src_dir = os.path.join(kernel_launchers_dir, "shared")
            shutil.copytree(src=src_dir, dst=target_dir, dirs_exist_ok=True)
        # When the launcher_dir_name is 'scala', we need to copy the toree jar (if determined), and
        # remove the toree-launcher source code from the staging dir.
        if launcher_dir_name in [SCALA]:
            if self.toree_jar_path:
                shutil.copyfile(
                    self.toree_jar_path,
                    os.path.join(target_dir, "lib", os.path.basename(self.toree_jar_path)),
                )
            scala_src_dir = os.path.join(target_dir, "toree-launcher")
            if os.path.isdir(scala_src_dir):
                self._delete_directory(scala_src_dir)

        # The source launcher 'scripts' directory may contain a __pycache__ directory.
        # Check for this condition in the staging area and delete the directory if present.
        pycache_dir = os.path.join(target_dir, "scripts", "__pycache__")
        if os.path.isdir(pycache_dir):
            self._delete_directory(pycache_dir)

    def log_and_exit(self, msg, exit_status=1):
        """Logs the msg as an error and exits with the given exit-status."""
        self.log.error(msg)
        self.exit(exit_status)

    @staticmethod
    def _create_staging_directory(parent_dir=None):
        """Creates a temporary staging directory at the specified location.

        If no `parent_dir` is specified, the platform-specific "temp" directory is used.
        """
        return tempfile.mkdtemp(prefix="staging_", dir=parent_dir)

    @staticmethod
    def _delete_directory(dir_name):
        """Deletes the specified directory."""
        shutil.rmtree(dir_name)

    @staticmethod
    def import_item(name: str) -> Any:
        """
        Import and return ``bar`` given the string ``foo.bar``.
        Calling ``bar = import_item("foo.bar")`` is the functional equivalent of
        executing the code ``from foo import bar``.

        :param name : string
          The fully qualified name of the module/package being imported.

        :returns mod : module object
           The module that was imported.
        """

        parts = name.rsplit(".", 1)
        if len(parts) == 2:
            # called with 'foo.bar....'
            package, obj = parts
            module = __import__(package, fromlist=[obj])
            try:
                pak = getattr(module, obj)
            except AttributeError as ae:
                err_msg = f"No module named '{obj}'"
                raise ImportError(err_msg) from ae
            return pak
        else:
            # called with un-dotted string
            return __import__(parts[0])

    @staticmethod
    def _get_tag() -> str:
        """Determines the tag to use for images based on the version.

        If the version indicates a development version, the tag will be "dev",
        else the tag will represent the version, including pre-releases like 2.0.0rc1
        """
        if "dev" in __version__:
            return "dev"
        return __version__


class BaseSpecApp(RemoteProvisionerConfigMixin, BaseApp):
    kernel_name = Unicode(
        config=True, help="""Install the kernel spec into a directory with this name."""
    )

    display_name = Unicode(
        config=True,
        help="""The display name of the kernel - used by user-facing applications.""",
    )

    language = Unicode(
        "Python",
        config=True,
        help="""The language of the kernel referenced in the kernel specification.  Must be one of
    'Python', 'R', or 'Scala'.  Default = 'Python'.""",
    )

    @validate("language")
    def _language_validate(self, proposal: dict[str, str]) -> str:
        value = proposal["value"]
        try:
            assert value.lower() in SUPPORTED_LANGUAGES
        except AssertionError as ae:
            err_msg = f"Invalid language value {value}, not in {SUPPORTED_LANGUAGES}"
            raise TraitError(err_msg) from ae
        return value

    ipykernel_subclass_name = Unicode(
        DEFAULT_PYTHON_KERNEL_CLASS_NAME,
        config=True,
        help="""For Python kernels, the name of the ipykernel subclass.""",
    )

    spark_home = Unicode(
        os.getenv("SPARK_HOME", "/opt/spark"),
        config=True,
        help="""Specify where the spark files can be found.""",
    )

    spark_init_mode = Unicode(
        DEFAULT_INIT_MODE,
        config=True,
        help=f"""Spark context initialization mode.  Must be one of {SPARK_INIT_MODES}.
    Default = {DEFAULT_INIT_MODE}.""",
    )

    @validate("spark_init_mode")
    def _spark_init_mode_validate(self, proposal: dict[str, str]) -> str:
        value = proposal["value"]
        try:
            assert value.lower() in SPARK_INIT_MODES
        except AssertionError as ae:
            err_msg = (
                f"Invalid Spark initialization mode value '{value}', not in {SPARK_INIT_MODES}"
            )
            raise TraitError(err_msg) from ae
        return value.lower()  # always use lowercase form

    extra_spark_opts = Unicode("", config=True, help="Specify additional Spark options.")

    # Flags
    user = Bool(
        False,
        config=True,
        help="Try to install the kernel spec to the per-user directory instead of the system "
        "or environment directory.",
    )

    prefix = Unicode(
        "",
        config=True,
        help="Specify a prefix to install to, e.g. an env. The kernelspec will be "
        "installed in PREFIX/share/jupyter/kernels/",
    )

    spark = Bool(False, config=True, help="Install kernel for use with Spark.")

    super_aliases = {
        "prefix": "BaseSpecApp.prefix",
        "kernel-name": "BaseSpecApp.kernel_name",
        "display-name": "BaseSpecApp.display_name",
        "language": "BaseSpecApp.language",
        "spark-home": "BaseSpecApp.spark_home",
        "spark-init-mode": "BaseSpecApp.spark_init_mode",
        "extra-spark-opts": "BaseSpecApp.extra_spark_opts",
        "authorized-users": "BaseSpecApp.authorized_users",
        "unauthorized-users": "BaseSpecApp.unauthorized_users",
        "port-range": "BaseSpecApp.port_range",
        "launch-timeout": "BaseSpecApp.launch_timeout",
        "ipykernel-subclass-name": "BaseSpecApp.ipykernel_subclass_name",
    }
    super_aliases.update(base_aliases)

    super_flags = {
        "user": (
            {"BaseSpecApp": {"user": True}},
            "Install to the per-user kernel registry",
        ),
        "sys-prefix": (
            {"BaseSpecApp": {"prefix": sys.prefix}},
            "Install to Python's sys.prefix. Useful in conda/virtual environments.",
        ),
        "spark": (
            {"BaseSpecApp": {"spark": True}},
            "Install kernelspec with Spark support.",
        ),
        "debug": base_flags["debug"],
    }

    @overrides
    def validate_parameters(self):
        if self.user and self.prefix:
            self.log_and_exit("Can't specify both user and prefix. Please choose one or the other.")

        if self.ipykernel_subclass_name != DEFAULT_PYTHON_KERNEL_CLASS_NAME:
            if self.language.lower() != PYTHON:
                self.log.warning(
                    "--ipykernel_subclass_name will be ignored since --language is not Python."
                )
            else:  # Attempt to validate the value is a subclass of ipykernel, but only warn if ImportError
                try:
                    from ipykernel.ipkernel import IPythonKernel

                    ipykernel_subclass = self.import_item(self.ipykernel_subclass_name)
                    if not issubclass(ipykernel_subclass, IPythonKernel):
                        self.log_and_exit(
                            f"Parameter ipykernel-subclass-name of '{self.ipykernel_subclass_name}' "
                            f"does not appear to be a subclass of '{DEFAULT_PYTHON_KERNEL_CLASS_NAME}'"
                        )
                except ImportError:
                    self.log.warning(
                        f"Cannot determine if parameter ipykernel-subclass-name "
                        f"'{self.ipykernel_subclass_name}' is a subclass of "
                        f"'{DEFAULT_PYTHON_KERNEL_CLASS_NAME}'.  Continuing..."
                    )

    @overrides
    def detect_missing_extras(self):
        if self.launcher_dir_name in [SCALA]:
            self._detect_missing_toree_jar()

        if self.launcher_dir_name in [R]:
            self._detect_missing_rscript()

    @overrides
    def install_files(self):
        """Assembles kernel-specs, launchers and resources into staging directory, then installs as kernel-spec."""

        # create staging dir
        staging_dir = self._create_staging_directory()

        # copy appropriate resource files
        self._copy_kernel_spec_files(staging_dir)

        # install to destination
        self.log.info(f"Installing kernel specification for '{self.display_name}'")
        self.install_dir = self.kernel_spec_manager.install_kernel_spec(
            staging_dir,
            kernel_name=self.kernel_name,
            user=self.user,
            prefix=self.prefix,
        )
        self._delete_directory(staging_dir)
        # If we're installing a scala kernel and don't have the toree jar file, issue
        # a warning indicating that the scala kernel needs that file in its kernelspec
        # directory hierarchy.
        if self.launcher_dir_name in [SCALA] and not self.toree_jar_path:
            kspec_toree_jar_location = os.path.join(self.install_dir, "lib")
            self.log.warning(
                "The Apache Toree kernel is either not installed or it's jar file cannot be determined. "
                f"Please ensure that the Toree jar file is placed into '{kspec_toree_jar_location}' "
                f"prior to using the kernel."
            )

        # Apply substitutions to kernel.json file
        self._finalize_kernel_json()

    def _copy_kernel_spec_files(self, staging_dir: str):
        """Copies the launcher, resource and kernel-spec files to the staging directory."""

        if any(
            dir_name is None
            for dir_name in [
                self.launcher_dir_name,
                self.resource_dir_name,
                self.kernel_spec_dir_name,
            ]
        ):
            err_msg = (
                "Invalid parameters.  Each of launcher_dir_name, resource_dir_name, "
                "and kernel_spec_dir_name must have a value!"
            )
            raise ValueError(err_msg)

        if self.launcher_dir_name not in launcher_dirs:
            err_msg = (
                f"Invalid launcher_dir_name '{self.launcher_dir_name}' "
                f"detected! Must be one of: {launcher_dirs}"
            )
            raise ValueError(err_msg)

        if self.resource_dir_name not in resource_dirs:
            err_msg = (
                f"Invalid resource_dir_name '{self.resource_dir_name}' "
                f"detected! Must be one of: {resource_dirs}"
            )
            raise ValueError(err_msg)

        # Copy the launcher files
        self._copy_launcher_files(self.launcher_dir_name, staging_dir)

        # Copy the resource files
        src_dir = os.path.join(kernel_resources_dir, self.resource_dir_name)
        shutil.copytree(src=src_dir, dst=staging_dir, dirs_exist_ok=True)

        # Copy the kernel-spec files
        src_dir = os.path.join(kernel_specs_dir, self.kernel_spec_dir_name)
        shutil.copytree(src=src_dir, dst=staging_dir, dirs_exist_ok=True)

    def _finalize_kernel_json(self):
        """Apply substitutions to the kernel.json string, update a kernel spec using these values,
        then write to the target kernel.json file.
        """
        subs = self.get_substitutions(self.install_dir)
        kernel_json_str = ""
        with open(os.path.join(self.install_dir, KERNEL_JSON)) as f:
            for line in f:
                line = line.split("#", 1)[0]
                kernel_json_str = kernel_json_str + line
            f.close()
        post_subs = Template(kernel_json_str).safe_substitute(subs)
        kernel_json = json.loads(post_subs)

        # Instantiate default KernelSpec, then update with the substitutions.  This allows for new fields
        # to be added that we might not yet know about.
        kernel_spec = KernelSpec().to_dict()
        kernel_spec.update(kernel_json)

        # Add ad-hoc config entries if set...
        if not kernel_spec["metadata"]["kernel_provisioner"].get("config"):
            kernel_spec["metadata"]["kernel_provisioner"]["config"] = {}
        self.add_optional_config_entries(kernel_spec["metadata"]["kernel_provisioner"]["config"])

        kernel_json_file = os.path.join(self.install_dir, KERNEL_JSON)
        self.log.debug(f"Finalizing kernel json file for kernel: '{self.display_name}'")
        with open(kernel_json_file, "w+") as f:
            json.dump(kernel_spec, f, indent=2)
            f.write("\n")

    def add_optional_config_entries(self, config_stanza: dict) -> None:
        """
        Adds optional configuration parameters to the 'config' stanza of 'kernel_provisioner'.

        This method is overridden by subclasses which should call super().add_optional_config_entries().
        """
        if self.authorized_users and list(self.authorized_users) != self.authorized_users_default():
            config_stanza["authorized_users"] = list(self.authorized_users)
        if (
            self.unauthorized_users
            and list(self.unauthorized_users) != self.unauthorized_users_default()
        ):
            config_stanza["unauthorized_users"] = list(self.unauthorized_users)
        if self.port_range and self.port_range != self.port_range_default_value:
            config_stanza["port_range"] = self.port_range
        if self.launch_timeout:  # Always add launch_timeout if there's a value.
            config_stanza["launch_timeout"] = self.launch_timeout

    def get_substitutions(self, install_dir: os.path) -> dict:
        """
        Gather substitution strings to inject into the templated files.

        This method is overridden by subclasses which should first call super().get_substitutions().
        """
        substitutions = {}
        substitutions["spark_home"] = self.spark_home
        substitutions["extra_spark_opts"] = self.extra_spark_opts
        substitutions["spark_init_mode"] = self.spark_init_mode
        substitutions["display_name"] = self.display_name
        substitutions["install_dir"] = install_dir
        substitutions["language"] = LANGUAGE_SUBSTITUTIONS[self.language.lower()]
        substitutions["ipykernel_subclass_name"] = self.ipykernel_subclass_name
        return substitutions
