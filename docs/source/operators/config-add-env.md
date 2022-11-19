# Additional environment variables

Besides those environment variables associated with configurable options, the following environment variables can also be used to influence functionality:

```text
  RP_DEFAULT_KERNEL_SERVICE_ACCOUNT_NAME=default
    Kubernetes Provisioners only.  This value indicates the default service account name to use for
    kernel namespaces when the KubernetesProvisioner needs to create the kernel's namespace
    and KERNEL_SERVICE_ACCOUNT_NAME has not been provided.

  RP_DOCKER_NETWORK=bridge
    Docker and Docker Swarm Provisioners only. Used by the docker deployment and launch
    scripts, this indicates the name of the docker network docker network to use.  The
    docker kernel launcher (launch_docker.py) defaults this value to 'bridge' only in
    cases where it wasn't previously set by the deployment script.

  RP_ENABLE_TUNNELING=False
    Indicates whether tunneling (via ssh) of the kernel and communication ports
    is enabled (True) or not (False).

  RP_KERNEL_CLUSTER_ROLE=kernel-controller or cluster-admin
    Kubernetes Provisioners only.  The role to use when binding with the kernel service
    account. The rp-clusterrole.yaml file creates the cluster role 'kernel-controller'
    and conveys that name via RP_KERNEL_CLUSTER_ROLE.  Should the deployment script
    not set this value, the KubernetesProvisioner will then use 'cluster-admin'.  It is
    recommended this value be set to something other than 'cluster-admin'.

  RP_KERNEL_LAUNCH_TIMEOUT=30
    The time (in seconds) hosting application will wait for a remote kernel's startup
    completion status before deeming the startup a failure.

  RP_KERNEL_LOG_DIR=/tmp
    The directory used during remote kernel launches of DistributedProvisioner
    kernels.  Files in this directory will be of the form kernel-<kernel_id>.log.

  RP_MAX_PORT_RANGE_RETRIES=5
    The number of attempts made to locate an available port within the specified
    port range.  Only applies when c.RemoteProvisionerConfigMixin.port_range
    (or RP_PORT_RANGE) has been specified or is in use for the given kernel.

  RP_MIN_PORT_RANGE_SIZE=1000
    The minimum port range size permitted when c.RemoteProvisionerConfigMixin.port_range
    (or RP_PORT_RANGE) is specified or is in use for the given kernel.  Port ranges
    reflecting smaller sizes will result in a failure to launch the corresponding
    kernel (since port-range can be specified within individual kernel specifications).

  RP_MIRROR_WORKING_DIRS=False
    Container-based Provisioners only.  If True, kernel creation requests that specify
    KERNEL_WORKING_DIR will set the kernel container's working directory to that value.
    See also KERNEL_WORKING_DIR.

  RP_NAMESPACE=default
    Kubernetes Provisioners only.  Used during Kubernetes deployment, this indicates
    the name of the namespace in which the hosting service is deployed.  The namespace
    is created prior to deployment, and is set into the RP_NAMESPACE env via
    deployment.yaml script. This value is then used within the KubernetesProvisioner to
    coordinate kernel configurations. Should this value not be set during deployment,
    the KubernetesProvisioner will default its value to namespace 'default'.

  RP_PROHIBITED_GIDS=0
    Container-based Provisioners only.  A comma-separated list of group ids (GID) whose
    values are not allowed to be referenced by KERNEL_GID.  This defaults to the root
    group id (0). Attempts to launch a kernel where KERNEL_GID's value is in this list
    will result in an exception indicating error 403 (Forbidden).  See also RP_PROHIBITED_UIDS.

  RP_PROHIBITED_LOCAL_IPS=''
    A comma-separated list of local IPv4 addresses (or regular expressions) that
    should not be used when determining the response address used to convey connection
    information back to the host server from a remote kernel.  In some cases, other
    network interfaces (e.g., docker with 172.17.0.*) can interfere - leading to
    connection failures during kernel startup.
    Example: RP_PROHIBITED_LOCAL_IPS=172.17.0.*,192.168.0.27 will eliminate the use
    of all addresses in 172.17.0 as well as 192.168.0.27

  RP_PROHIBITED_UIDS=0
    Container-based Provisioners only.  A comma-separated list of user ids (UID) whose
    values are not allowed to be referenced by KERNEL_UID.  This defaults to the root
    user id (0).  Attempts to launch a kernel where KERNEL_UID's value is in this list
    will result in an exception indicating error 403 (Forbidden).  See also RP_PROHIBITED_GIDS.

  RP_RESPONSE_IP=None
    The IP address to use to formulate the response address (with `RP_RESPONSE_PORT`).
    By default, the server's IP is used.  However, we may find it necessary to use a
    different IP in cases where the target kernels are external to the host server
    (for example).  It's value may also need to be set in cases where the computed
    (default) is not correct for the current topology.

  RP_RESPONSE_PORT=8877
    The single response port used to receive connection information from
    launched kernels.

  RP_RESPONSE_PORT_RETRIES=10
    The number of retries to attempt when the original response port
    (RP_RESPONSE_PORT) is found to be in-use.  This value should be
    set to 0 (zero) if no port retries are desired.

  RP_SHARED_NAMESPACE=True
    Kubernetes Provisioners only. This value indicates whether (True) or not (False) all
    kernel pods should reside in the same namespace as the hosting server.  If the server
    is intended to support multiple users, it is recommended that this value be set to
    False for better isolation of kernel resources.

  RP_SSH_PORT=22
    Distributed Provisioners only. The port number used for ssh operations for installations
    choosing to configure the ssh server on a port other than the default 22.

  RP_REMOTE_PWD=None
    Distributed Provisioners only. The password to use to ssh to remote hosts.

  RP_REMOTE_USER=None
    Distributed Provisioners only. The username to use when connecting to remote hosts
    (default to `getpass.getuser()` when not set).

  RP_REMOTE_GSS_SSH=False
    Distributed Provisioners only. Use gss instead of RP_REMOTE_USER and RP_REMOTE_PWD to
    connect to remote host via SSH. Case insensitive. 'True' to enable, 'False', '' or
    unset to disable. Any other value will error.

  RP_YARN_CERT_BUNDLE=<custom_truststore_path>
    Yarn Provisioners only. The path to a .pem or any other custom truststore used as a CA
    bundle in yarn-api-client.
```
