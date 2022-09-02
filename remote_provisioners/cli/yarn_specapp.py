# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import os
import sys

from traitlets import Unicode, Bool, default
from traitlets.config.application import Application

from .._version import __version__
from .base_specapp import BaseSpecApp, DEFAULT_LANGUAGE, PYTHON, SCALA, R, DASK


DEFAULT_KERNEL_NAMES = {
    PYTHON: 'yarn_spark_python',
    SCALA: 'yarn_spark_scala',
    R: 'yarn_spark_r',
    DASK: 'yarn_dask_python'}
DEFAULT_DISPLAY_NAMES = {
    PYTHON: 'Spark Python (YARN Cluster)',
    SCALA: 'Spark Scala (YARN Cluster)',
    R: 'Spark R (YARN Cluster)',
    DASK: 'Dask Python (YARN Cluster)'}


class YarnSpecApp(BaseSpecApp):
    """CLI for extension management."""
    name = "jupyter-yarn-spec"
    description = "Creates a Jupyter kernel specification for use within a Hadoop Yarn cluster."
    # Note that the left justification of the second example is necessary to ensure proper
    # alignment with the first example during --help output.
    examples = """
    jupyter-yarn-spec install --language=R --spark-home=/usr/local/spark
    
jupyter-yarn-spec install --kernel-name=dask_python --dask --yarn-endpoint=http://foo.bar:8088/ws/v1/cluster

jupyter-yarn-spec install --language=Scala --spark-init-mode eager
    """

    @default("kernel_name")
    def kernel_name_default(self) -> str:
        return DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]

    @default("display_name")
    def display_name_default(self) -> str:
        return DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]

    # Yarn endpoint
    yarn_endpoint_env = 'RP_YARN_ENDPOINT'
    yarn_endpoint = Unicode(None, config=True, allow_none=True,
                            help="""The http url specifying the YARN Resource Manager. Note: If this value is NOT set,
the YARN library will use the files within the local HADOOP_CONFIG_DIR to determine the
active resource manager. (RP_YARN_ENDPOINT env var)""")

    @default('yarn_endpoint')
    def yarn_endpoint_default(self):
        return os.getenv(self.yarn_endpoint_env)

    # Alt Yarn endpoint
    alt_yarn_endpoint_env = 'RP_ALT_YARN_ENDPOINT'
    alt_yarn_endpoint = Unicode(None, config=True, allow_none=True,
                                help="""The http url specifying the alternate YARN Resource Manager.  This value should
be set when YARN Resource Managers are configured for high availability.  Note: If both
YARN endpoints are NOT set, the YARN library will use the files within the local
HADOOP_CONFIG_DIR to determine the active resource manager.
(RP_ALT_YARN_ENDPOINT env var)""")

    @default('alt_yarn_endpoint')
    def alt_yarn_endpoint_default(self):
        return os.getenv(self.alt_yarn_endpoint_env)

    python_root = Unicode(sys.prefix, config=True,
                          help="Specify where the root of the python installation resides (parent dir of bin/python).")

    extra_dask_opts = Unicode('', config=True, help="Specify additional Dask options.")

    # Flags
    # Yarn endpoint security enabled
    yarn_endpoint_security_enabled_env = 'RP_YARN_ENDPOINT_SECURITY_ENABLED'
    yarn_endpoint_security_enabled_default_value = False
    yarn_endpoint_security_enabled = Bool(yarn_endpoint_security_enabled_default_value, config=True,
                                          help="""Is YARN Kerberos/SPNEGO Security enabled (True/False).
(RP_YARN_ENDPOINT_SECURITY_ENABLED env var)""")

    @default('yarn_endpoint_security_enabled')
    def yarn_endpoint_security_enabled_default(self):
        return bool(os.getenv(self.yarn_endpoint_security_enabled_env,
                              self.yarn_endpoint_security_enabled_default_value))

    # Impersonation enabled
    impersonation_enabled_env = 'RP_IMPERSONATION_ENABLED'
    impersonation_enabled = Bool(False, config=True,
                                 help="""Indicates whether impersonation will be performed during kernel launch.
(RP_IMPERSONATION_ENABLED env var)""")

    @default('impersonation_enabled')
    def impersonation_enabled_default(self):
        return bool(os.getenv(self.impersonation_enabled_env, 'false').lower() == 'true')

    dask = Bool(False, config=True, help="Kernelspec will be configured for Dask YARN.")

    aliases = {
        'yarn-endpoint': 'YarnSpecApp.yarn_endpoint',
        'alt-yarn-endpoint': 'YarnSpecApp.alt_yarn_endpoint',
        'python-root': 'YarnSpecApp.python_root',
        'extra-dask-opts': 'YarnSpecApp.extra_dask_opts',
    }
    aliases.update(BaseSpecApp.super_aliases)

    flags = {
        'dask': ({'YarnSpecApp': {'dask': True}}, "Install kernelspec for Dask in Yarn cluster."),
        'yarn-endpoint-security-enabled': ({'YarnSpecApp': {'yarn_endpoint_security_enabled': True}},
                                           "Install kernelspec where Yarn API endpoint has security enabled."),
        'impersonation-enabled': ({'YarnSpecApp': {'impersonation_enabled': True}},
                                  "Install kernelspec to impersonate user (requires root privileges)."),
    }
    flags.update(BaseSpecApp.super_flags)

    def validate_parameters(self):
        """Validate input parameters and prepare for their injection into templated files."""
        super().validate_parameters()

        entered_language = self.language
        self.language = self.language.lower()
        self.launcher_dir_name = self.language
        self.resource_dir_name = self.language

        if self.dask:
            if self.language != PYTHON:
                self.log.warning("Dask support only works with Python, changing language from {} to Python.".
                                 format(entered_language))
                self.language = PYTHON
            # if kernel and display names are still defaulted, silently change to dask defaults
            if self.kernel_name == DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]:
                self.kernel_name = DEFAULT_KERNEL_NAMES[DASK]
            if self.display_name == DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]:
                self.display_name = DEFAULT_DISPLAY_NAMES[DASK]

            self.kernel_spec_dir_name = DEFAULT_KERNEL_NAMES[DASK]
            self.spark_init_mode = 'none'
            if len(self.extra_spark_opts) > 0:
                self.log.warning("--extra_spark_opts will be ignored for Dask-based kernelspecs.")
                self.extra_spark_opts = ''
        else:
            # if kernel and display names are still defaulted, silently change to language defaults
            if self.kernel_name == DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]:
                self.kernel_name = DEFAULT_KERNEL_NAMES[self.language]
            if self.display_name == DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]:
                self.display_name = DEFAULT_DISPLAY_NAMES[self.language]

            self.kernel_spec_dir_name = DEFAULT_KERNEL_NAMES[self.language]
            if len(self.extra_dask_opts) > 0:
                self.log.warning("--extra_dask_opts will be ignored for Spark-based kernelspecs.")
                self.extra_dask_opts = ''

        # sanitize kernel_name
        self.kernel_name = self.kernel_name.replace(' ', '_')

    def add_optional_config_entries(self, config_stanza: dict) -> None:
        """Adds optional configuration parameters to the 'config' stanza of 'kernel_provisioner'."""
        super().add_optional_config_entries(config_stanza)
        if self.yarn_endpoint and self.yarn_endpoint != self.yarn_endpoint_default():
            config_stanza["yarn_endpoint"] = self.yarn_endpoint
        if self.alt_yarn_endpoint and self.alt_yarn_endpoint != self.alt_yarn_endpoint_default():
            config_stanza["alt_yarn_endpoint"] = self.alt_yarn_endpoint
        if self.yarn_endpoint_security_enabled and \
                self.yarn_endpoint_security_enabled != self.yarn_endpoint_security_enabled_default():
            config_stanza["yarn_endpoint_security_enabled"] = self.yarn_endpoint_security_enabled

    def get_substitutions(self, install_dir) -> dict:
        """Gather substitution strings to inject into the templated files."""
        substitutions = super().get_substitutions(install_dir)
        substitutions['extra_dask_opts'] = self.extra_dask_opts
        substitutions['python_root'] = self.python_root
        substitutions['py4j_path'] = ''

        # If this is a python kernel, attempt to get the path to the py4j file.
        if self.language == PYTHON and not self.dask:
            try:
                python_lib_contents = os.listdir(f"{self.spark_home}/python/lib")
                py4j_zip = list(filter(lambda filename: "py4j" in filename, python_lib_contents))[0]

                # This is always a sub-element of a path, so let's prefix with colon
                substitutions['py4j_path'] = f":{self.spark_home}/python/lib/{py4j_zip}"
            except OSError:
                self.log.warn('Unable to find py4j, installing without PySpark support.')
        return substitutions


class YarnProvisionerApp(Application):
    """Application responsible for driving the creation of Yarn-based kernel specifications."""
    version = __version__
    name = "jupyter yarn-spec"
    description = """Application used to create kernel specifications for use on Hadoop Yarn clusters 
    via the YarnProvisioner kernel provisioner."""
    subcommands = dict({'install': (YarnSpecApp, YarnSpecApp.description.splitlines()[0]), })
    aliases = {}
    flags = {}

    def start(self):
        if self.subapp is None:
            print('No subcommand specified. Must specify one of: {}'.format(list(self.subcommands)))
            print()
            self.print_description()
            self.print_subcommands()
            self.exit(1)
        else:
            return self.subapp.start()


if __name__ == '__main__':
    YarnProvisionerApp.launch_instance()
