# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import os

from jupyter_core.application import JupyterApp
from overrides import overrides
from traitlets import List, Unicode, default

from .._version import __version__
from .base_app import DEFAULT_LANGUAGE, PYTHON, SCALA, BaseSpecApp, R

DEFAULT_KERNEL_NAMES = {PYTHON: "ssh_python", SCALA: "ssh_scala", R: "ssh_r"}
DEFAULT_DISPLAY_NAMES = {PYTHON: "Python SSH", SCALA: "Scala SSH", R: "R SSH"}
SPARK_SUFFIX = "_spark"
SPARK_DISPLAY_NAME_SUFFIX = " (with Spark)"


class SshSpecInstaller(BaseSpecApp):
    """CLI for extension management."""

    name = "jupyter-ssh-spec"
    description = (
        "Creates a Jupyter kernel specification for use within a cluster of hosts via SSH."
    )
    # Note that the left justification of the second example is necessary to ensure proper
    # alignment with the first example during --help output.
    examples = """
    jupyter-ssh-spec install --language R --spark --spark-master spark://192.168.2.5:7077 --spark-home=/usr/local/spark

jupyter-ssh-spec install --kernel-name ssh_python --remote-hosts=192.168.2.4 --remote-hosts=192.168.2.5

jupyter-ssh-spec install --language Scala --spark --spark_init_mode 'eager'
    """

    @default("kernel_name")
    def _kernel_name_default(self) -> str:
        return DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]

    @default("display_name")
    def _display_name_default(self) -> str:
        return DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]

    remote_hosts_env = "GP_REMOTE_HOSTS"
    remote_hosts_default_value = "localhost"
    remote_hosts = List(
        default_value=[remote_hosts_default_value],
        config=True,
        help="""List of host names on which this kernel can be launched.  Multiple entries must
each be specified via separate options: --remote-hosts host1 --remote-hosts host2""",
    )

    @default("remote_hosts")
    def _remote_hosts_default(self):
        return os.getenv(self.remote_hosts_env, self.remote_hosts_default_value).split(",")

    spark_master_default_value = "yarn"
    spark_master = Unicode(
        default_value=spark_master_default_value,
        config=True,
        help="Specify the Spark Master URL (e.g., 'spark://HOST:PORT' or 'yarn'.",
    )
    # Flags

    aliases = {
        "remote-hosts": "SshSpecInstaller.remote_hosts",
        "spark-master": "SshSpecInstaller.spark_master",
    }
    aliases.update(BaseSpecApp.super_aliases)

    flags = {}
    flags.update(BaseSpecApp.super_flags)

    @overrides
    def validate_parameters(self):
        super().validate_parameters()

        self.language = self.language.lower()
        self.launcher_dir_name = self.language
        self.resource_dir_name = self.language

        if self.spark is True:
            # if kernel and display names are still defaulted, silently convert to lang default and append spark suffix
            if self.kernel_name == DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]:
                self.kernel_name = DEFAULT_KERNEL_NAMES[self.language] + SPARK_SUFFIX
            if self.display_name == DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]:
                self.display_name = DEFAULT_DISPLAY_NAMES[self.language] + SPARK_DISPLAY_NAME_SUFFIX

            self.kernel_spec_dir_name = DEFAULT_KERNEL_NAMES[self.language] + SPARK_SUFFIX
        else:
            # if kernel and display names are still defaulted, silently change to language defaults
            if self.kernel_name == DEFAULT_KERNEL_NAMES[DEFAULT_LANGUAGE]:
                self.kernel_name = DEFAULT_KERNEL_NAMES[self.language]
            if self.display_name == DEFAULT_DISPLAY_NAMES[DEFAULT_LANGUAGE]:
                self.display_name = DEFAULT_DISPLAY_NAMES[self.language]
            self.kernel_spec_dir_name = DEFAULT_KERNEL_NAMES[self.language]

            self.spark_init_mode = "none"
            if len(self.extra_spark_opts) > 0:
                self.log.warning(
                    "--extra_spark_opts will be ignored since --spark has not been specified."
                )
                self.extra_spark_opts = ""

        # sanitize kernel_name
        self.kernel_name = self.kernel_name.replace(" ", "_")

    @overrides
    def add_optional_config_entries(self, config_stanza: dict) -> None:
        super().add_optional_config_entries(config_stanza)
        if self.remote_hosts and list(self.remote_hosts) != self.remote_hosts_default():
            config_stanza["remote_hosts"] = list(self.remote_hosts)

    @overrides
    def get_substitutions(self, install_dir) -> dict:
        substitutions = super().get_substitutions(install_dir)
        substitutions["spark_master"] = self.spark_master
        return substitutions


class SshProvisionerApp(JupyterApp):
    """Application responsible for driving the creation of Ssh-based kernel specifications."""

    version = __version__
    name = "jupyter ssh-spec"
    description = """Application used to create kernel specifications for use on clusters via SSH
    and the DistributedProvisioner kernel provisioner."""
    subcommands = dict(
        {
            "install": (SshSpecInstaller, SshSpecInstaller.description.splitlines()[0]),
        }
    )
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
    SshProvisionerApp.launch_instance()
