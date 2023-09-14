# Distributed deployments

Distributed deployments will utilize the [`DistributedProvisioner`](../contributors/system-architecture.md#distributedprovisioner)
to launch kernels across a distributed set of hosts via SSH.

Steps required to complete deployment on a distributed cluster are:

1. Ensure passwordless SSH is configured between hosts.
1. Install the host application on the primary node of the distributed cluster.
1. [Install Gateway Provisioners](installing-gp.md#distributedssh) where the host application is located.
1. [Install the desired kernels](installing-kernels.md).
1. Generate the desired kernel specifications ([see below](#generating-kernel-specifications)) and replicate those
   specifications across the cluster.
1. If necessary, configure the host application and generated kernel specifications relative to the
   `DistributedProvisioner`'s [configurable options](config-file.md), [environment variables](config-add-env.md), and
   [per-kernel overrides](config-kernel-override.md#distributedprovisioner-per-kernel-overrides).
1. Launch the host application.

## Prerequisites

The distributed capabilities of the `DistributedProvisioner` utilize SSH.  As a result, you must ensure appropriate
password-less functionality is in place.

If you want to use Spark in "client mode", you'll want to ensure the `SPARK_HOME` environment variable is properly
configured.

- `SPARK_HOME` must point to the Apache Spark installation path

```text
SPARK_HOME:/usr/hdp/current/spark2-client  # For HDP distribution
```

Although the set of remote hosts can be specified on a per-kernel basis, it's probably best to define the complete
set of remote hosts in the host application via `c.DistributedProvisioner.remote_hosts` or env `GP_REMOTE_HOSTS`.

```{tip}
Entries in the remote hosts configuration should be fully qualified domain names (FQDN). For
example, `host1.acme.com, host2.acme.com`
```

The `DistributedProvisioner` supports [two forms of load-balancing](#specifying-a-load-balancing-algorithm),
round-robin (the default) and least-connection. If you wish to use least-connection, you'll want to configure
that as well.

## Generating Kernel Specifications

Gateway Provisioners provides the `jupyter-ssh-spec` to generate kernel specifications for the `DistributedProvisioner`.

```{admonition} Important!
:class: warning
All kernel *specifications* configured to use the `DistributedProvisioner` must reside on all
nodes to which there's a reference in the remote hosts configuration and located in the same location
as they appear on the primary node!  As a result, it is recommended they first be generated on the primary
node, then copied (in their entirety) to each applicable node of the cluster.
```

```{tip}
Each node of the cluster will typically be configured in the same manner relative to directory
hierarchies and environment variables.  As a result, you may find it easier to get kernel
specifications working on one node, then, after confirming their operation, copy them to
other nodes and update the remote-hosts configuration to include the other nodes.  You will
still need to _install_ the kernels themselves on each node.
```

To generate a default kernel specification (where Python is the default kernel) enter:

```bash
jupyter ssh-spec install
```

which produces the following output...

```text
[I 2023-02-08 16:21:50.254 SshSpecInstaller] Installing kernel specification for 'Python SSH'
[I 2023-02-08 16:21:50.485 SshSpecInstaller] Installed kernelspec ssh_python in /usr/local/share/jupyter/kernels/ssh_python
```

and the following set of files and directories:

```text
/usr/local/share/jupyter/kernels/ssh_python
kernel.json logo-64x64.png

/usr/local/share/jupyter/kernels/ssh_python/scripts:
launch_ipykernel.py server_listener.py
```

where each provides the following function:

- `kernel.json` - the primary file that the host application uses to discover a given kernel's availability.
  This file contains _stanzas_ that describe the kernel's argument vector (`argv`), its runtime environment (`env`),
  its display name (`display_name`) and language (`language`), as
  well as its kernel provisioner's configuration (`metadata.kernel_provisioner`) - which, in this case, will reflect the
  `DistributedProvisioner`.
- `logo-64x64.png` - the icon resource corresponding to this kernel specification.  Icon resource files must be start
  with the `logo-` prefix to be included in the kernel specification.
- `scripts/launch_ipykernel.py` - the "launcher" for the IPyKernel kernel (or subclasses thereof).  This file is typically
  implemented in the language of the kernel and is responsible for creating the local connection information, asynchronously
  starting a SparkContext (if asked), spawning a listener process to receive interrupts and shutdown requests, and starting
  the IPyKernel itself.
- `scripts/server_listener.py` - utilized by both Python and R kernels, this file is responsible for encrypting the
  connection information and sending it back to the host application, then listening for interrupt and shutdown requests.

```{note}
If generating the kernel specification for use with Spark "client mode" (by specifying the `'--spark'` option), you'll
also have:
- `bin/run.sh` - this script sets up and invokes the `spark-submit`
command that is responsible for interacting with the Spark cluster.  When `'--spark'` is specified `run.sh` will be the
first entry in the `kernel.json`'s `argv` stanza,
```

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

### Adjusting Kernel Specifications

While many options can be specified via command-line options to `jupyter ssh-spec install`, there may be times when
manual adjustments are necessary.

After generating the kernel specifications, you should have a `kernel.json` that resembles the
following (this one is relative to the Python kernel using defaulted parameters):

```json
{
  "argv": [
    "python",
    "/usr/local/share/jupyter/kernels/ssh_python/scripts/launch_ipykernel.py",
    "--kernel-id",
    "{kernel_id}",
    "--port-range",
    "{port_range}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--kernel-class-name",
    "ipykernel.ipkernel.IPythonKernel"
  ],
  "env": {},
  "display_name": "Python SSH",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "debugger": true,
    "kernel_provisioner": {
      "provisioner_name": "distributed-provisioner",
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
`bin/run.sh` file (when specifying `'--spark'`) - although changes are not typically necessary.

### Command-line options

The following is produced using `jupyter ssh-spec install --help` and displays the complete set of command-line options.

```text
Creates a Jupyter kernel specification for use within a cluster of hosts via
SSH.

Options
=======
The options below are convenience aliases to configurable class-options,
as listed in the "Equivalent to" description-line of the aliases.
To see all configurable class-options for some <cmd>, use:
    <cmd> --help-all

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
--remote-hosts=<list-item-1>...
    List of host names on which this kernel can be launched.  Multiple entries
    must each be specified via separate options: --remote-hosts host1 --remote-
    hosts host2
    Default: ['localhost']
    Equivalent to: [--SshSpecInstaller.remote_hosts]
--spark-master=<Unicode>
    Specify the Spark Master URL (e.g., 'spark://HOST:PORT' or 'yarn'.
    Default: 'yarn'
    Equivalent to: [--SshSpecInstaller.spark_master]
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

    jupyter-ssh-spec install --language R --spark --spark-master spark://192.168.2.5:7077 --spark-home=/usr/local/spark

    jupyter-ssh-spec install --kernel-name ssh_python --remote-hosts=192.168.2.4 --remote-hosts=192.168.2.5

    jupyter-ssh-spec install --language Scala --spark --spark_init_mode 'eager'

To see all available configurables, use `--help-all`.
```

## Specifying a load-balancing algorithm

The `DistributedProvisioner` provides two ways to configure how kernels are distributed across
the configured set of hosts: round-robin or least-connection.  This configurable option is a _host application_
setting and is not available to be overridden on a per-kernel basis.

### Round-robin

The round-robin algorithm simply uses an index into the set of configured hosts, incrementing
the index on each kernel startup so that it points to the next host in the configured set. To
specify the use of round-robin, use one of the following:

_Configuration_:

```python
c.DistributedProvisioner.load_balancing_algorithm = "round-robin"
```

_Environment_:

```bash
export GP_LOAD_BALANCING_ALGORITHM=round-robin
```

Since _round-robin_ is the default load-balancing algorithm, this option is not necessary.

### Least-connection

The least-connection algorithm tracks the hosts that are currently servicing kernels spawned by
the server instance. Using this information, the `DistributedProvisioner` selects the host with
the least number of kernels. It does not consider other information, or whether there is _another_
server instance using the same set of hosts. To specify the use of least-connection, use one of
the following:

_Configuration_:

```python
c.DistributedProvisioner.load_balancing_algorithm = "least-connection"
```

_Environment_:

```bash
export GP_LOAD_BALANCING_ALGORITHM=least-connection
```

### Pinning a kernel to a host

A kernel's start request can specify a specific remote host on which to run by specifying that
host in the `KERNEL_REMOTE_HOST` environment variable within the request's body. When specified,
the configured load-balancing algorithm will be by-passed and the kernel will be started on the
specified host.

## Spark Support

The `DistributedProvisioner` can be used within Spark clusters although using the `YarnProvisioner` to accomplish this
is recommended since the _Spark driver_ is essentially scheduled based on resource consumption within the cluster.
Nevertheless, there are some scenarios where YARN client mode or Spark standalone configurations make sense.

### YARN Client Mode

YARN client mode kernel specifications can be considered _distributed mode kernels_. They just
happen to use `spark-submit` from different nodes in the cluster but use the
`DistributedProvisioner` to manage their lifecycle.

These kernel specifications are generated using the `'--spark'` command line option as noted above.  When provided,
a kernel specification similar to the following is produced:

```json
{
  "argv": [
    "/usr/local/share/jupyter/kernels/ssh_python_spark/bin/run.sh",
    "--kernel-id",
    "{kernel_id}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--port-range",
    "{port_range}",
    "--spark-context-initialization-mode",
    "lazy",
    "--kernel-class-name",
    "ipykernel.ipkernel.IPythonKernel"
  ],
  "env": {
    "SPARK_HOME": "/opt/spark",
    "PYSPARK_PYTHON": "/opt/conda/bin/python",
    "PYTHONPATH": "${HOME}/.local/lib/python3.7/site-packages:/usr/hdp/current/spark2-client/python:/usr/hdp/current/spark2-client/python/lib/py4j-0.10.6-src.zip",
    "SPARK_OPTS": "--master yarn --deploy-mode client --name ${KERNEL_ID:-ERROR__NO__KERNEL_ID} ${KERNEL_EXTRA_SPARK_OPTS}",
    "LAUNCH_OPTS": ""
  },
  "display_name": "Python SSH (with Spark)",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "debugger": true,
    "kernel_provisioner": {
      "provisioner_name": "distributed-provisioner",
      "config": {
        "launch_timeout": 30
      }
    }
  }
}
```

Make any necessary adjustments such as updating `SPARK_HOME` or other environment and path
specific configurations.

### Spark Standalone

Although `jupyter-ssh-spec install` does not have an option to configure the `DistributedProvisioner` for use within
a standalone Spark cluster, the following steps can be used to adjust a YARN Client Mode specification to Spark standalone.

- Make a copy of the source `ssh_python_spark` kernelspec into an applicable `ssh_python_spark_standalone` directory.
- Edit the `kernel.json` file:
  - Update the display_name with e.g. `Spark - Python (Spark Standalone)`.
  - Update the `--master` option in the SPARK_OPTS to point to the spark master node
    rather than indicate `--deploy-mode client`.
  - Update the `argv` stanza to reference `run.sh` in the appropriate directory.

After that, you should have a `kernel.json` that looks similar to this:

```json
{
  "argv": [
    "/usr/local/share/jupyter/kernels/ssh_python_spark_standalone/bin/run.sh",
    "--kernel-id",
    "{kernel_id}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}"
  ],
  "env": {
    "SPARK_HOME": "/opt/spark",
    "PYSPARK_PYTHON": "/opt/conda/bin/python",
    "PYTHONPATH": "${HOME}/.local/lib/python3.7/site-packages:/usr/hdp/current/spark2-client/python:/usr/hdp/current/spark2-client/python/lib/py4j-0.10.6-src.zip",
    "SPARK_OPTS": "--master spark://127.0.0.1:7077  --name ${KERNEL_ID:-ERROR__NO__KERNEL_ID}",
    "LAUNCH_OPTS": ""
  },
  "language": "python",
  "display_name": "Python SSH (with Spark Standalone)",
  "metadata": {
    "kernel_provisioner": {
      "provisioner_name": "distributed-provisioner"
    }
  }
}
```
