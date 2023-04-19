# Hadoop YARN deployments

Hadoop YARN deployments will utilize the `YarnProvisioner` to launch kernels across the cluster via
the YARN resource manager.  The following assumes a Hadoop Yarn cluster has already been provisioned.

```{note}
In some cases, where a Spark "client mode" is desired, use of the `DistributedProvisioner`
will be leveraged. Please refer to the [_Distributed deployments_](deploy-distributed.md) topic
for those details.
```

Steps required to complete deployment on a Hadoop YARN cluster are:

1. Install the host application on the primary node of the Hadoop YARN cluster.
1. [Install Gateway Provisioners](installing-gp.md#hadoop-yarn) where the host application is located. Note,
   this location is not a hard-requirement, but recommended.
   If installed remotely, some extra configuration will be necessary relative to the Hadoop configuration.
1. [Install the desired kernels](installing-kernels.md).
1. Generate the desired kernel specifications ([see below](#generating-kernel-specifications)).
1. If necessary, configure the host application and generated kernel specifications relative to the
   `YarnProvisioner`'s [configurable options](config-file.md), [environment variables](config-add-env.md), and
   [per-kernel overrides](config-kernel-override.md#yarnprovisioner-per-kernel-overrides).
1. Launch the host application.

## Prerequisites

The distributed capabilities are currently based on an Apache Spark cluster utilizing Hadoop
YARN as the resource manager and thus require the following environment variables to be set
to facilitate the integration between Apache Spark and Hadoop YARN components:

- `SPARK_HOME` must point to the Apache Spark installation path

```bash
export SPARK_HOME=/usr/hdp/current/spark2-client  # For HDP distribution
```

- `GP_YARN_ENDPOINT` must point to the YARN resource manager endpoint if the host application is
  remote from the YARN cluster

```bash
export GP_YARN_ENDPOINT=http://${YARN_RESOURCE_MANAGER_FQDN}:8088/ws/v1/cluster
```

```{note}
If the server is using an applicable `HADOOP_CONF_DIR` that contains a valid `yarn-site.xml` file,
then this config value can remain unset (default = None) and the YARN client library will locate
the appropriate resource manager from the configuration.  This is also true in cases where the
YARN cluster is configured for high availability.
```

If the server is remote from the YARN cluster (i.e., no `HADOOP_CONF_DIR`) and the YARN cluster is
configured for high availability, then the alternate endpoint should also be specified...

```bash
export GP_ALT_YARN_ENDPOINT=http://${ALT_YARN_RESOURCE_MANAGER_FQDN}:8088/ws/v1/cluster #Common to YARN deployment
```

## Generating Kernel Specifications

Gateway Provisioners provides the `jupyter-yarn-spec` to generate kernel specifications for the `YarnProvisioner`.

To generate a default kernel specification (where Python is the default kernel) enter:

```bash
jupyter yarn-spec install
```

which produces the following output...

```text
[I 2023-02-08 09:48:48.685 YarnSpecInstaller] Installing kernel specification for 'Spark Python (YARN Cluster)'
[I 2023-02-08 09:48:49.048 YarnSpecInstaller] Installed kernelspec yarn_spark_python in /usr/local/share/jupyter/kernels/yarn_spark_python
```

and the following set of files and directories:

```text
/usr/local/share/jupyter/kernels/yarn_spark_python
kernel.json logo-64x64.png

/usr/local/share/jupyter/kernels/yarn_spark_python/bin:
run.sh

/usr/local/share/jupyter/kernels/yarn_spark_python/scripts:
launch_ipykernel.py server_listener.py
```

where each provides the following function:

- `kernel.json` - the primary file that the host application uses to discover a given kernel's availability.
  This file contains _stanzas_ that describe the kernel's argument vector (`argv`), its runtime environment (`env`),
  its display name (`display_name`) and language (`language`), as
  well as its kernel provisioner's configuration (`metadata.kernel_provisioner`) - which, in this case, will reflect the
  `YarnProvisioner`.
- `logo-64x64.png` - the icon resource corresponding to this kernel specification.  Icon resource files must be start
  with the `logo-` prefix to be included in the kernel specification.
- `bin/run.sh` - the first entry in the `kernel.json`'s `argv` stanza, this script sets up and invokes the `spark-submit`
  command that is responsible for interacting with the Hadoop Yarn Resource Manager.  The `YarnProvisioner` then
  _discovers_ the location of where the kernel (Spark driver) was scheduled to run to complete the kernel's startup.
- `scripts/launch_ipykernel.py` - the "launcher" for the IPyKernel kernel (or subclasses thereof).  This file is typically
  implemented in the language of the kernel and is responsible for creating the local connection information, asynchronously
  starting a SparkContext (if asked), spawning a listener process to receive interrupts and shutdown requests, and starting
  the IPyKernel itself.
- `scripts/server_listener.py` - utilized by both Python and R kernels, this file is responsible for encrypting the
  connection information and sending it back to the host application, then listening for interrupt and shutdown requests.

```{note}
R-based kernel specifications will see a `scripts/launch_IRkernel.R` script alongside `server_listener.py`, while
Scala-based specifications will, instead, have a `lib` directory containing jar files for both the scala launcher
(`toree-launcher-SCALA_VERSION.jar` and includes equivalent functionality to `server_listener.py`) and the Apache
toree kernel (`toree-assembly-TOREE_VERSION.jar`)
```

```{tip}
For shared environments (typical in Gateway server deployments) we recommend installing kernel specifications
into a shared folder like `/usr/local/share/jupyter/kernels` (which is the default).  This is the location in
which they reside within container images and where many of the document references assume they'll be located.

Alternate locations can be specified via option `--user` (which places the set of files within the invoking user's
home directory structure) or option `--sys-prefix` (which places the set of files within the active python
environment's directory structure).
```

```{admonition} Important!
:class: warning
With the `YarnProvisioner`, only the Python and R kernel _packages_ are required on each node,
not the entire kernel specification (i.e., the kernel installation files).  For Scala (Apache Toree)
kernels, the kernel package is included in the `spark-submit` command and copied to each node
(if not already there) as noted above.
```

### Adjusting Kernel Specifications

While many options can be specified via command-line options to `jupyter yarn-spec install`, there may be times when
manual adjustments are necessary.

After generating the kernel specifications, you should have a `kernel.json` that resembles the
following (this one is relative to the Python kernel using defaulted parameters):

```json
{
  "argv": [
    "/usr/local/share/jupyter/kernels/yarn_spark_python/bin/run.sh",
    "--kernel-id",
    "{kernel_id}",
    "--port-range",
    "{port_range}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--spark-context-initialization-mode",
    "lazy",
    "--kernel-class-name",
    "ipykernel.ipkernel.IPythonKernel"
  ],
  "env": {
    "SPARK_HOME": "/opt/spark",
    "PYSPARK_PYTHON": "/opt/miniconda3/envs/provisioners/bin/python",
    "PYTHONPATH": "${HOME}/.local/lib/python3.7/site-packages:/opt/spark/python",
    "SPARK_OPTS": "--master yarn --deploy-mode cluster --name ${KERNEL_ID:-ERROR__NO__KERNEL_ID} --conf spark.yarn.submit.waitAppCompletion=false --conf spark.yarn.appMasterEnv.PYTHONUSERBASE=/home/${KERNEL_USERNAME}/.local --conf spark.yarn.appMasterEnv.PYTHONPATH=${HOME}/.local/lib/python3.7/site-packages:/opt/spark/python --conf spark.yarn.appMasterEnv.PATH=/opt/miniconda3/envs/provisioners/bin:$PATH  ${KERNEL_EXTRA_SPARK_OPTS}",
    "LAUNCH_OPTS": ""
  },
  "display_name": "Spark Python (YARN Cluster)",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "kernel_provisioner": {
      "provisioner_name": "yarn-provisioner",
      "config": {
        "launch_timeout": 30
      }
    }
  }
}
```

The `metadata` and `argv` entries for each kernel specification should be nearly identical and
not require changes. You will need to adjust the `env` entries to apply to your specific
configuration.

You should also check the same kinds of environment and path settings in the corresponding
`bin/run.sh` file - although changes are not typically necessary.

### Command-line Options

The following is produced using `jupyter yarn-spec install --help` and displays the complete set of command-line
options:

```text
Creates a Jupyter kernel specification for use within a Hadoop Yarn cluster.

Options
=======
The options below are convenience aliases to configurable class-options,
as listed in the "Equivalent to" description-line of the aliases.
To see all configurable class-options for some <cmd>, use:
    <cmd> --help-all

--dask
    Install kernelspec for Dask in Yarn cluster.
    Equivalent to: [--YarnSpecInstaller.dask=True]
--yarn-endpoint-security-enabled
    Install kernelspec where Yarn API endpoint has security enabled.
    Equivalent to: [--YarnSpecInstaller.yarn_endpoint_security_enabled=True]
--impersonation-enabled
    Install kernelspec to impersonate user (requires root privileges).
    Equivalent to: [--YarnSpecInstaller.impersonation_enabled=True]
--user
    Install to the per-user kernel registry
    Equivalent to: [--BaseSpecApp.user=True]
--sys-prefix
    Install to Python's sys.prefix. Useful in conda/virtual environments.
    Equivalent to: [--BaseSpecApp.prefix=/opt/miniconda3/envs/provisioners]
--spark
    Install kernelspec with Spark support.
    Equivalent to: [--BaseSpecApp.spark=True]
--debug
    set log level to logging.DEBUG (maximize logging output)
    Equivalent to: [--Application.log_level=10]
--yarn-endpoint=<Unicode>
    The http url specifying the YARN Resource Manager. Note: If this value is
    NOT set, the YARN library will use the files within the local
    HADOOP_CONFIG_DIR to determine the active resource manager.
    (GP_YARN_ENDPOINT env var)
    Default: None
    Equivalent to: [--YarnSpecInstaller.yarn_endpoint]
--alt-yarn-endpoint=<Unicode>
    The http url specifying the alternate YARN Resource Manager.  This value
    should be set when YARN Resource Managers are configured for high
    availability.  Note: If both YARN endpoints are NOT set, the YARN library
    will use the files within the local HADOOP_CONFIG_DIR to determine the
    active resource manager. (GP_ALT_YARN_ENDPOINT env var)
    Default: None
    Equivalent to: [--YarnSpecInstaller.alt_yarn_endpoint]
--python-root=<Unicode>
    Specify where the root of the python installation resides (parent dir of
    bin/python).
    Default: '/opt/miniconda3/envs/provisioners'
    Equivalent to: [--YarnSpecInstaller.python_root]
--extra-dask-opts=<Unicode>
    Specify additional Dask options.
    Default: ''
    Equivalent to: [--YarnSpecInstaller.extra_dask_opts]
--prefix=<Unicode>
    Specify a prefix to install to, e.g. an env. The kernelspec will be
    installed in PREFIX/share/jupyter/kernels/
    Default: ''
    Equivalent to: [--BaseSpecApp.prefix]
--kernel-name=<Unicode>
    Install the kernel spec into a directory with this name.
    Default: ''
    Equivalent to: [--BaseSpecApp.kernel_name]
--display-name=<Unicode>
    The display name of the kernel - used by user-facing applications.
    Default: ''
    Equivalent to: [--BaseSpecApp.display_name]
--language=<Unicode>
    The language of the kernel referenced in the kernel specification.  Must be one of
        'Python', 'R', or 'Scala'.  Default = 'Python'.
    Default: 'Python'
    Equivalent to: [--BaseSpecApp.language]
--spark-home=<Unicode>
    Specify where the spark files can be found.
    Default: '/opt/spark'
    Equivalent to: [--BaseSpecApp.spark_home]
--spark-init-mode=<Unicode>
    Spark context initialization mode.  Must be one of ['lazy', 'eager', 'none'].
        Default = lazy.
    Default: 'lazy'
    Equivalent to: [--BaseSpecApp.spark_init_mode]
--extra-spark-opts=<Unicode>
    Specify additional Spark options.
    Default: ''
    Equivalent to: [--BaseSpecApp.extra_spark_opts]
--authorized-users=<set-item-1>...
    List of user names against which KERNEL_USERNAME will be compared. Any match
    (case-sensitive) will allow the kernel's launch, otherwise an HTTP 403
    (Forbidden) error will be raised.  The set of unauthorized users takes
    precedence. This option should be used carefully as it can dramatically
    limit who can launch kernels. To specify multiple names via the CLI,
    separate options must be provided for each entry. (GP_AUTHORIZED_USERS env
    var - non-bracketed, just comma-separated)
    Default: set()
    Equivalent to: [--BaseSpecApp.authorized_users]
--unauthorized-users=<set-item-1>...
    List of user names against which KERNEL_USERNAME will be compared. Any match
    (case-sensitive) will prevent the kernel's launch and result in an HTTP 403
    (Forbidden) error. To specify multiple names via the CLI, separate options
    must be provided for each entry. (GP_UNAUTHORIZED_USERS env var - non-
    bracketed, just comma-separated)
    Default: {'root'}
    Equivalent to: [--BaseSpecApp.unauthorized_users]
--port-range=<Unicode>
    Specifies the lower and upper port numbers from which ports are created. The
    bounded values are separated by '..' (e.g., 33245..34245 specifies a range
    of 1000 ports to be randomly selected). A range of zero (e.g., 33245..33245
    or 0..0) disables port-range enforcement.  (GP_PORT_RANGE env var)
    Default: '0..0'
    Equivalent to: [--BaseSpecApp.port_range]
--launch-timeout=<Int>
    Number of ports to try if the specified port is not available
    (GP_LAUNCH_TIMEOUT env var)
    Default: 30
    Equivalent to: [--BaseSpecApp.launch_timeout]
--ipykernel-subclass-name=<Unicode>
    For Python kernels, the name of the ipykernel subclass.
    Default: 'ipykernel.ipkernel.IPythonKernel'
    Equivalent to: [--BaseSpecApp.ipykernel_subclass_name]
--log-level=<Enum>
    Set the log level by value or name.
    Choices: any of [0, 10, 20, 30, 40, 50, 'DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL']
    Default: 30
    Equivalent to: [--Application.log_level]
--config=<Unicode>
    Full path of a config file.
    Default: ''
    Equivalent to: [--JupyterApp.config_file]

Examples
--------

    jupyter-yarn-spec install --language=R --spark-home=/usr/local/spark

    jupyter-yarn-spec install --kernel-name=dask_python --dask --yarn-endpoint=http://foo.bar:8088/ws/v1/cluster

    jupyter-yarn-spec install --language=Scala --spark-init-mode eager

To see all available configurables, use `--help-all`.
```
