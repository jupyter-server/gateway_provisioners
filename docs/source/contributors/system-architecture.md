# System Architecture

Below are sections presenting details of the Gateway Provisioners internals and other related items. While we will attempt to maintain its consistency, the ultimate answers are in the code itself.

## Gateway Provisioners

Process proxy classes derive from the abstract base class `BaseProvisionerABC` - which defines the four basic
process methods. There are two immediate subclasses of `BaseProvisionerABC` - `LocalProvisioner`
and `RemoteProvisionerBase`.

`LocalProvisioner` is essentially a pass-through to the current implementation. Kernel specifications that do not contain
a `process_proxy` stanza will use `LocalProvisioner`.

`RemoteProvisionerBase` is an abstract base class representing remote kernel processes. Currently, there are seven
built-in subclasses of `RemoteProvisionerBase` ...

- `DistributedProvisioner` - largely a proof of concept class, `DistributedProvisioner` is responsible for the launch
  and management of kernels distributed across an explicitly defined set of hosts using ssh. Hosts are determined
  via a round-robin algorithm (that we should make pluggable someday).
- `YarnProvisioner` - is responsible for the discovery and management of kernels hosted as Hadoop YARN applications
  within a managed cluster.
- `KubernetesProvisioner` - is responsible for the discovery and management of kernels hosted
  within a Kubernetes cluster.
- `DockerSwarmProvisioner` - is responsible for the discovery and management of kernels hosted
  within a Docker Swarm cluster.
- `DockerProvisioner` - is responsible for the discovery and management of kernels hosted
  within Docker configuration. Note: because these kernels will always run local to the corresponding Enterprise Gateway instance, these process proxies are of limited use.
- `ConductorClusterProvisioner` - is responsible for the discovery and management of kernels hosted
  within an IBM Spectrum Conductor cluster.
- `SparkOperatorProvisioner` - is responsible for the discovery and management of kernels hosted
  within a Kubernetes cluster but created as a `SparkApplication` instead of a Pod. The `SparkApplication` is a Kubernetes custom resource
  defined inside the project [spark-on-k8s-operator](https://github.com/GoogleCloudPlatform/spark-on-k8s-operator), which
  makes all kinds of spark on k8s components better organized and easy to configure.

```{note}
Before you run a kernel associated with `SparkOperatorProvisioner`, ensure that the [Kubernetes Operator for Apache Spark is installed](https://github.com/GoogleCloudPlatform/spark-on-k8s-operator#installation) in your Kubernetes cluster.
```

You might notice that the last six process proxies do not necessarily control the _launch_ of the kernel. This is
because the native jupyter framework is utilized such that the script that is invoked by the framework is what
launches the kernel against that particular resource manager. As a result, the _startup time_ actions of these process
proxies is more about discovering where the kernel _landed_ within the cluster in order to establish a mechanism for
determining lifetime. _Discovery_ typically consists of using the resource manager's API to locate the kernel whose name includes its kernel ID
in some fashion.

On the other hand, the `DistributedProvisioner` essentially wraps the kernel specification's argument vector (i.e., invocation
string) in a remote shell since the host is determined by Enterprise Gateway, eliminating the discovery step from
its implementation.

These class definitions can be found in the
[processproxies package](https://github.com/jupyter-server/enterprise_gateway/blob/main/enterprise_gateway/services/processproxies). However,
Enterprise Gateway is architected such that additional process proxy implementations can be provided and are not
required to be located within the Enterprise Gateway hierarchy - i.e., we embrace a _bring your own process proxy_ model.

![Process Class Hierarchy](../images/process_proxy_hierarchy.png)

### RemoteProvisionerBase

As noted above, `RemoteProvisionerBase` is an abstract base class that derives from `BaseProvisionerABC`. Subclasses
of `RemoteProvisionerBase` must implement two methods - `confirm_remote_startup()` and `handle_timeout()`:

```python
@abstractmethod
def confirm_remote_startup(self, kernel_cmd, **kw):
```

where

- `kernel_cmd` is a list (argument vector) that should be invoked to launch the kernel. This parameter is an
  artifact of the kernel manager `_launch_kernel()` method.
- `**kw` is a set key-word arguments.

`confirm_remote_startup()` is responsible for detecting that the remote kernel has been appropriately launched and is ready to receive requests. This can include gathering application status from the remote resource manager but is really a function of having received the connection information from the remote kernel launcher. (See [Kernel Launchers](#kernel-launchers))

```python
@abstractmethod
def handle_timeout(self):
```

`handle_timeout()` is responsible for detecting that the remote kernel has failed to startup in an acceptable time. It
should be called from `confirm_remote_startup()`. If the timeout expires, `handle_timeout()` should throw HTTP
Error 500 (`Internal Server Error`).

Kernel launch timeout expiration is expressed via the environment variable `KERNEL_LAUNCH_TIMEOUT`. If this
value does not exist, it defaults to the Enterprise Gateway process environment variable `EG_KERNEL_LAUNCH_TIMEOUT` - which
defaults to 30 seconds if unspecified. Since all `KERNEL_` environment variables "flow" from the Notebook server, the launch
timeout can be specified as a client attribute of the Notebook session.

#### YarnProvisioner

As part of its base offering, Enterprise Gateway provides an implementation of a process proxy that communicates with the Hadoop YARN resource manager that has been instructed to launch a kernel on one of its worker nodes. The node on which the kernel is launched is up to the resource manager - which enables an optimized distribution of kernel resources.

Derived from `RemoteProvisionerBase`, `YarnProvisioner` uses the `yarn-api-client` library to locate the kernel and monitor its lifecycle. However, once the kernel has returned its connection information, the primary kernel operations naturally take place over the ZeroMQ ports.

This process proxy is reliant on the `--EnterpriseGatewayApp.yarn_endpoint` command line option or the `EG_YARN_ENDPOINT` environment variable to determine where the YARN resource manager is located. To accommodate increased flexibility, the endpoint definition can be defined within the process proxy stanza of the kernel specification, enabling the ability to direct specific kernels to different YARN clusters.

In cases where the YARN cluster is configured for high availability, then the `--EnterpriseGatewayApp.alt_yarn_endpoint` command line option or the `EG_ALT_YARN_ENDPOINT` environment variable should also be defined. When set, the underlying `yarn-api-client` library will choose the active Resource Manager between the two.

```{note}
If Enterprise Gateway is running on an edge node of the cluster and has a valid `yarn-site.xml` file in HADOOP_CONF_DIR, neither of these values are required (default = None).  In such cases, the `yarn-api-client` library will choose the active Resource Manager from the configuration files.
```

```{seealso}
[Hadoop YARN deployments](../operators/deploy-yarn-cluster.md) in the Operators Guide for details.
```

#### DistributedProvisioner

Like `YarnProvisioner`, Gateway Provisioners also provides an implementation of a basic
round-robin remoting mechanism that is part of the `DistributedProvisioner` class. This class
uses the `c.DistributedProvisioner.remote_hosts` configuration option (or `GP_REMOTE_HOSTS`
environment variable) to determine on which hosts a given kernel should be launched. It uses
a basic round-robin algorithm to index into the list of remote hosts for selecting the target
host. It then uses ssh to launch the kernel on the target host. As a result, all kernel specification
files must reside on the remote hosts in the same directory structure as on the Enterprise
Gateway server.

It should be noted that kernels launched with this process proxy run in YARN _client_ mode - so their
resources (within the kernel process itself) are not managed by the Hadoop YARN resource manager.

Like the yarn endpoint parameter the `remote_hosts` parameter can be specified within the
process proxy configuration to override the global value - enabling finer-grained kernel distributions.

```{seealso}
[Distributed deployments](../operators/deploy-distributed.md) in the Operators Guide for details.
```

#### KubernetesProvisioner

With the popularity of Kubernetes within the enterprise, Gateway Provisioners provides an implementation
of a process proxy that communicates with the Kubernetes resource manager via the Kubernetes API. Unlike
the other offerings, in the case of Kubernetes, Enterprise Gateway is itself deployed within the Kubernetes
cluster as a _Service_ and _Deployment_. The primary vehicle by which this is accomplished is via [Helm](https://helm.sh/) and Enterprise Gateway provides a set of [helm chart](https://github.com/jupyter-server/enterprise_gateway/tree/main/etc/kubernetes/helm/enterprise-gateway) files to simplify deployment.

```{seealso}
[Kubernetes deployments](../operators/deploy-kubernetes.md) in the Operators Guide for details.
```

#### DockerSwarmProvisioner

Gateway Provisioners provides an implementation of a process proxy that communicates with the Docker Swarm resource manager via the Docker API. When used, the kernels are launched as swarm services and can reside anywhere in the managed cluster. To leverage kernels configured in this manner, Enterprise Gateway can be deployed
either as a Docker Swarm _service_ or a traditional Docker container.

A similar `DockerProvisioner` implementation has also been provided. When used, the corresponding kernel will be launched as a traditional docker container that runs local to the launching Enterprise Gateway instance. As a result, its use has limited value.

```{seealso}
[Docker and Docker Swarm deployments](../operators/deploy-docker.md) in the Operators Guide for details.
```

#### CustomResourceProvisioner

Gateway Provisioners also provides a implementation of a process proxy derived from `KubernetesProvisioner`
called `CustomResourceProvisioner`.

Instead of creating kernels based on a Kubernetes pod, `CustomResourceProvisioner`
manages kernels via a custom resource definition (CRD). For example, `SparkApplication` is a CRD that includes
many components of a Spark-on-Kubernetes application.

If you are going to extend `CustomResourceProvisioner`, just follow steps below:

- override custom resource related variables(i.e. `group`, `version` and `plural`
  and `get_container_status` method, wrt [launch_kubernetes.py](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernel-launchers/kubernetes/scripts/launch_kubernetes.py).

- define a jinja template like
  [kernel-pod.yaml.j2](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2).
  As a generic design, the template file should be named as {crd_group}-{crd_version} so that you can reuse
  [launch_kubernetes.py](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernel-launchers/kubernetes/scripts/launch_kubernetes.py) in the kernelspec.

- define a kernel specification like [spark_python_operator/kernel.json](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernelspecs/spark_python_operator/kernel.json).

### Gateway Provisioners Configuration

Each `kernel.json`'s `kernel_provisioner` stanza can specify an optional `config` stanza that is converted
into a dictionary of name/value pairs and passed as an argument to each kernel provisioner's constructor
relative to the provisioner identified by the `provisioner_name` entry.

How each dictionary entry is interpreted is completely a function of the constructor relative to that provisioner
class or its superclass. For example, an alternate list of remote hosts has meaning to the `DistributedProvisioner` but
not to its superclasses. As a result, the superclass constructors will not attempt to interpret that value.

In addition, certain dictionary entries can override or amend system-level configuration values set on the command-line, thereby
allowing administrators to tune behaviors down to the kernel level. For example, an administrator might want to
constrain Python kernels configured to use specific resources to an entirely different set of hosts (and ports) that other
remote kernels might be targeting in order to isolate valuable resources. Similarly, an administrator might want to
only authorize specific users to a given kernel.

In such situations, one might find the following `kernel_provisioner` stanza:

```json
{
  "metadata": {
    "kernel_provisioner": {
      "provisioner_name": "distributed-provisioner",
      "config": {
        "remote_hosts": "priv_host1,priv_host2",
        "port_range": "40000..41000",
        "authorized_users": "bob,alice"
      }
    }
  }
}
```

In this example, the kernel associated with this `kernel.json` file is relegated to the hosts `priv_host1` and `priv_host2`
where kernel ports will be restricted to a range between `40000` and `41000` and only users `bob` and `alice` can
launch such kernels (provided neither appear in the global set of `unauthorized_users` since denial takes precedence).

For a current enumeration of which system-level configuration values can be overridden or amended on a per-kernel basis
see [Per-kernel overrides](../operators/config-kernel-override.md).

## Kernel Launchers

As noted above, a kernel is considered started once the `launch_process()` method has conveyed its connection
information back to the Gateway Provisioner's server process. Conveyance of connection information
from a remote kernel is the responsibility of the remote kernel _launcher_.

Kernel launchers provide a means of normalizing behaviors across kernels while avoiding kernel
modifications. Besides providing a location where connection file creation can occur, they also
provide a 'hook' for other kinds of behaviors - like establishing virtual environments or
sandboxes, providing collaboration behavior, adhering to port range restrictions, etc.

There are four primary tasks of a kernel launcher:

1. Creation of the connection file and ZMQ ports on the remote (target) system along with a _server listener_ socket
2. Conveyance of the connection (and listener socket) information back to the Gateway Provisioner's server process
3. Invocation of the target kernel
4. Listen for interrupt and shutdown requests from the Gateway Provisioner's server and carry out the action when appropriate

Kernel launchers are minimally invoked with three parameters (all of which are conveyed by the `argv` stanza of the corresponding `kernel.json` file) - the kernel's ID as created by the server and conveyed via the placeholder `{kernel_id}`, a response address consisting of the Gateway Provisioner's server's IP and port on which to return the connection information similarly represented by the placeholder `{response_address}`, and a public-key used by the launcher to encrypt an AES key that encrypts the kernel's connection information back to the server and represented by the placeholder `{public_key}`.

The kernel's ID is identified by the parameter `--kernel-id`. Its value (`{kernel_id}`) is essentially used to build a connection file to pass to the to-be-launched kernel, along with any other things - like log files, etc.

The response address is identified by the parameter `--response-address`. Its value (`{response_address}`) consists of a string of the form `<IPV4:port>` where the IPV4 address points back to the Gateway Provisioner's server - which is listening for a response on the provided port. The port's default value is `8877`, but can be specified via the environment variable `GP_RESPONSE_PORT`.

The public key is identified by the parameter `--public-key`. Its value (`{public_key}`) is used to encrypt an AES key created by the launcher to encrypt the kernel's connection information. The server, upon receipt of the response, uses the corresponding private key to decrypt the AES key, which it then uses to decrypt the connection information. Both the public and private keys are ephemeral; created upon Enterprise Gateway's startup. They can be ephemeral because they are only needed during a kernel's startup and never again.

Here's a [kernel.json](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernelspecs/spark_python_yarn_cluster/kernel.json) file illustrating these parameters...

FIXME - the example is process-proxy

```json
{
  "language": "python",
  "display_name": "Spark - Python (YARN Cluster Mode)",
  "metadata": {
    "process_proxy": {
      "class_name": "enterprise_gateway.services.processproxies.yarn.YarnProvisioner"
    }
  },
  "env": {
    "SPARK_HOME": "/usr/hdp/current/spark2-client",
    "SPARK_OPTS": "--master yarn --deploy-mode cluster --name ${KERNEL_ID:-ERROR__NO__KERNEL_ID} --conf spark.yarn.submit.waitAppCompletion=false",
    "LAUNCH_OPTS": ""
  },
  "argv": [
    "/usr/local/share/jupyter/kernels/spark_python_yarn_cluster/bin/run.sh",
    "--kernel-id",
    "{kernel_id}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}"
  ]
}
```

Other options supported by launchers include:

- `--port-range {port_range}` - passes configured port-range to launcher where launcher applies that range to kernel ports. The port-range may be configured globally or on a per-kernel specification basis, as previously described.

- `--spark-context-initialization-mode [lazy|eager|none]` - indicates the _timeframe_ in which the spark context will be created.

  - `lazy` (default) attempts to defer initialization as late as possible - although this can vary depending on the
    underlying kernel and launcher implementation.
  - `eager` attempts to create the spark context as soon as possible.
  - `none` skips spark context creation altogether.

  Note that some launchers may not be able to support all modes. For example, the scala launcher uses the Apache Toree
  kernel - which currently assumes a spark context will exist. As a result, a mode of `none` doesn't apply.
  Similarly, the `lazy` and `eager` modes in the Python launcher are essentially the same, with the spark context
  creation occurring immediately, but in the background thereby minimizing the kernel's startup time.

Kernel.json files also include a `LAUNCH_OPTS:` section in the `env` stanza to allow for custom
parameters to be conveyed in the launcher's environment. `LAUNCH_OPTS` are then referenced in
the [run.sh](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernelspecs/spark_python_yarn_cluster/bin/run.sh)
script as the initial arguments to the launcher
(see [launch_ipykernel.py](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernel-launchers/python/scripts/launch_ipykernel.py)) ...

```bash
eval exec \
     "${SPARK_HOME}/bin/spark-submit" \
     "${SPARK_OPTS}" \
     "${PROG_HOME}/scripts/launch_ipykernel.py" \
     "${LAUNCH_OPTS}" \
     "$@"
```

## Extending Gateway Provisioners

Theoretically speaking, enabling a kernel for use in other frameworks amounts to the following:

1. Build a kernel specification file that identifies the provisioner class to be used.
2. Implement the provisioner class such that it supports the four primitive functions of
   `poll()`, `wait()`, `send_signal(signum)` and `kill()` along with `launch_process()`. If this
   provisioner derives from another, these method implementations can be inherited.
3. If the provisioner corresponds to a remote process, derive the provisioner class from
   `RemoteProvisionerBase` and implement `confirm_remote_startup()` and `handle_timeout()`.
4. Insert invocation of a launcher (if necessary) which builds the connection file and
   returns its contents on the `{response_address}` socket and following the encryption protocol set forth in the other launchers.

```{seealso}
This topic is covered in the [Developers Guide](../developers/index.rst).
```
