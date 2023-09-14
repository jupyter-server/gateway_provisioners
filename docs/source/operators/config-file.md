# Configuration options

Because Gateway Provisioners leverage the [`traitlets` package](https://traitlets.readthedocs.io/en/stable/),
configurable options can be defined
within the Jupyter-based application's configuration file - since it too will leverage `traitlets`.

For example, if Jupyter Server is the application hosting the Gateway Provisioners,
the configurable attributes would be defined within `jupyter_server_config.py`.

Here's an example configuration entry that could be used to set the `DistributedProvisioner`'s
`remote_hosts` value. Note that its default value, when defined, is also displayed, along with
the corresponding environment variable name:

```python
## Bracketed comma-separated list of hosts on which DistributedProvisioner
#  kernels will be launched e.g., ['host1','host2'].
#  (GP_REMOTE_HOSTS env var - non-bracketed, just comma-separated)
#  Default: ['localhost']
c.DistributedProvisioner.remote_hosts = ["localhost"]
```

## Provisioner-specific Configuration Options

A complete set of configuration options available for each Gateway Provisioner follows.  Where applicable, the
configurable option's default value is also provided.

### `KubernetesProvisioner`

```python
# ------------------------------------------------------------------------------
# KubernetesProvisioner(ContainerProvisionerBase) configuration
# ------------------------------------------------------------------------------
## Kernel lifecycle management for Kubernetes kernels.

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.authorized_users
# c.KubernetesProvisioner.authorized_users = set()

## The image name to use as the Spark executor image when launching
#  See also: ContainerProvisionerBase.executor_image_name
# c.KubernetesProvisioner.executor_image_name = None

## The image name to use when launching container-based kernels.
#  See also: ContainerProvisionerBase.image_name
# c.KubernetesProvisioner.image_name = None

## Number of ports to try if the specified port is not available
#  See also: RemoteProvisionerConfigMixin.launch_timeout
# c.KubernetesProvisioner.launch_timeout = 30

## Specifies the lower and upper port numbers from which ports are created.
#  See also: RemoteProvisionerConfigMixin.port_range
# c.KubernetesProvisioner.port_range = '0..0'

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.unauthorized_users
# c.KubernetesProvisioner.unauthorized_users = {'root'}
```

### `DockerSwarmProvisioner`

```python
# ------------------------------------------------------------------------------
# DockerSwarmProvisioner(ContainerProvisionerBase) configuration
# ------------------------------------------------------------------------------
## Kernel provisioner for kernels in Docker Swarm.

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.authorized_users
# c.DockerSwarmProvisioner.authorized_users = set()

## The image name to use as the Spark executor image when launching
#  See also: ContainerProvisionerBase.executor_image_name
# c.DockerSwarmProvisioner.executor_image_name = None

## The image name to use when launching container-based kernels.
#  See also: ContainerProvisionerBase.image_name
# c.DockerSwarmProvisioner.image_name = None

## Number of ports to try if the specified port is not available
#  See also: RemoteProvisionerConfigMixin.launch_timeout
# c.DockerSwarmProvisioner.launch_timeout = 30

## Specifies the lower and upper port numbers from which ports are created.
#  See also: RemoteProvisionerConfigMixin.port_range
# c.DockerSwarmProvisioner.port_range = '0..0'

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.unauthorized_users
# c.DockerSwarmProvisioner.unauthorized_users = {'root'}
```

### `DockerProvisioner`

```python
# ------------------------------------------------------------------------------
# DockerProvisioner(ContainerProvisionerBase) configuration
# ------------------------------------------------------------------------------
## Kernel provisioner for kernels in Docker (non-Swarm).

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.authorized_users
# c.DockerProvisioner.authorized_users = set()

## The image name to use as the Spark executor image when launching
#  See also: ContainerProvisionerBase.executor_image_name
# c.DockerProvisioner.executor_image_name = None

## The image name to use when launching container-based kernels.
#  See also: ContainerProvisionerBase.image_name
# c.DockerProvisioner.image_name = None

## Number of ports to try if the specified port is not available
#  See also: RemoteProvisionerConfigMixin.launch_timeout
# c.DockerProvisioner.launch_timeout = 30

## Specifies the lower and upper port numbers from which ports are created.
#  See also: RemoteProvisionerConfigMixin.port_range
# c.DockerProvisioner.port_range = '0..0'

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.unauthorized_users
# c.DockerProvisioner.unauthorized_users = {'root'}
```

### `DistributedProvisioner`

```python
# ------------------------------------------------------------------------------
# DistributedProvisioner(RemoteProvisionerBase) configuration
# ------------------------------------------------------------------------------
## Kernel lifecycle management for clusters via ssh and a set of hosts.

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.authorized_users
# c.DistributedProvisioner.authorized_users = set()

## Number of ports to try if the specified port is not available
#  See also: RemoteProvisionerConfigMixin.launch_timeout
# c.DistributedProvisioner.launch_timeout = 30

## Specifies which load balancing algorithm DistributedProvisioner should use.
#  Must be one of "round-robin" or "least-connection".
#  (GP_LOAD_BALANCING_ALGORITHM env var)
#  Default: 'round-robin'
# c.DistributedProvisioner.load_balancing_algorithm = 'round-robin'

## Specifies the lower and upper port numbers from which ports are created.
#  See also: RemoteProvisionerConfigMixin.port_range
# c.DistributedProvisioner.port_range = '0..0'

## List of host names on which this kernel can be launched.  Multiple entries
#  must each be specified via separate options: --remote-hosts host1 --remote-
#  hosts host2
#  Default: ['localhost']
# c.DistributedProvisioner.remote_hosts = ['localhost']

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.unauthorized_users
# c.DistributedProvisioner.unauthorized_users = {'root'}
```

### `YarnProvisioner`

```python
# ------------------------------------------------------------------------------
# YarnProvisioner(RemoteProvisionerBase) configuration
# ------------------------------------------------------------------------------
## Kernel lifecycle management for YARN clusters.

## The http url specifying the alternate YARN Resource Manager.  This value
#  should be set when YARN Resource Managers are configured for high
#  availability.  Note: If both YARN endpoints are NOT set, the YARN library will
#  use the files within the local HADOOP_CONFIG_DIR to determine the active
#  resource manager. (GP_ALT_YARN_ENDPOINT env var)
#  Default: None
# c.YarnProvisioner.alt_yarn_endpoint = None

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.authorized_users
# c.YarnProvisioner.authorized_users = set()

## Indicates whether impersonation will be performed during kernel launch.
#  (GP_IMPERSONATION_ENABLED env var)
#  Default: False
# c.YarnProvisioner.impersonation_enabled = False

## Number of ports to try if the specified port is not available
#  See also: RemoteProvisionerConfigMixin.launch_timeout
# c.YarnProvisioner.launch_timeout = 30

## Specifies the lower and upper port numbers from which ports are created.
#  See also: RemoteProvisionerConfigMixin.port_range
# c.YarnProvisioner.port_range = '0..0'

## List of user names against which KERNEL_USERNAME will be compared.
#  See also: RemoteProvisionerConfigMixin.unauthorized_users
# c.YarnProvisioner.unauthorized_users = {'root'}

## The http url specifying the YARN Resource Manager. Note: If this value is NOT
#  set, the YARN library will use the files within the local HADOOP_CONFIG_DIR to
#  determine the active resource manager. (GP_YARN_ENDPOINT env var)
#  Default: None
# c.YarnProvisioner.yarn_endpoint = None

## Is YARN Kerberos/SPNEGO Security enabled (True/False).
#  (GP_YARN_ENDPOINT_SECURITY_ENABLED env var)
#  Default: False
# c.YarnProvisioner.yarn_endpoint_security_enabled = False
```
