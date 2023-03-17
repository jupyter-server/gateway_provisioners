# Configuring security

This section introduces some security features inherent in Gateway Provisioners.

## KERNEL_USERNAME

In order to convey the name of the authenticated user, `KERNEL_USERNAME` should be sent in the
kernel creation request via the `env:` entry. This will occur automatically within the
gateway-enabled servers since it propagates all environment variables
prefixed with `KERNEL_`. If the request does not include a `KERNEL_USERNAME` entry, one will be
added to the kernel's launch environment with the value of the host server's user.

This value is then used within the _authorization_ and _impersonation_ functionality.

## Authorization

By default, all users are authorized to start kernels. This behavior can be adjusted when
situations arise where more control is required. Basic authorization can be expressed in two ways.

### Authorized Users

The configuration file option: `c.RemoteProvisionerConfigMixin.authorized_users` or `GP_AUTHORIZED_USERS` env
can be specified to contain a list of usernames indicating which users are permitted to launch
kernels within the current server.

On each kernel launched, the authorized users list is searched for the value of `KERNEL_USERNAME`
(case-sensitive). If the user is found in the list the kernel's launch sequence continues,
otherwise HTTP Error 403 (Forbidden) is raised and the request fails.

```{warning}
Since the `authorized_users` option must be exhaustive, it should be used only in situations where a small
and limited set of users are allowed access and empty otherwise.
```

### Unauthorized Users

The configuration file option: `c.RemoteProvisionerConfigMixin.unauthorized_users` or `GP_UNAUTHORIZED_USERS` env
can be specified to contain a list of usernames indicating which users are **NOT** permitted to
launch kernels within the current server. The `unauthorized_users` list is always checked prior
to the `authorized_users` list. If the value of `KERNEL_USERNAME` appears in the `unauthorized_users`
list, the request is immediately failed with the same 403 (Forbidden) HTTP Error.

From a system security standpoint, privileged users (e.g., `root` and any users allowed `sudo`
privileges) should be added to this option.

### Authorization Failures

It should be noted that the corresponding messages logged when each of the above authorization
failures occur are slightly different. This allows the administrator to discern from which
authorization list the failure was generated.

Failures stemming from _inclusion_ in the `unauthorized_users` list will include text similar to
the following:

```text
User 'bob' is not authorized to start kernel 'Spark - Python (YARN Mode)'. Ensure
KERNEL_USERNAME is set to an appropriate value and retry the request.
```

Failures stemming from _exclusion_ from a non-empty `authorized_users` list will include text
similar to the following:

```text
User 'bob' is not in the set of users authorized to start kernel 'Spark - Python (YARN Mode)'. Ensure
KERNEL_USERNAME is set to an appropriate value and retry the request.
```

## User Impersonation

Servers using `GatewayProvisioners` can leverage other technologies to implement user impersonation
when launching kernels. This option is configured via two pieces of information:
`GP_IMPERSONATION_ENABLED` and `KERNEL_USERNAME`.

`GP_IMPERSONATION_ENABLED` indicates the intention that user impersonation should be performed and
can also be conveyed via the boolean configuration option
`c.RemoteProvisionerConfigMixin.impersonation_enabled` (default = False).

`KERNEL_USERNAME` is also conveyed within the environment of the kernel launch sequence where
its value is used to indicate the user that should be impersonated.

### Impersonation in Hadoop YARN clusters

In a cluster managed by the Hadoop YARN resource manager, impersonation is implemented by leveraging
kerberos, and thus require this security option as a pre-requisite for user impersonation. When user
impersonation is enabled, kernels are launched with the `--proxy-user ${KERNEL_USERNAME}` which will
tell YARN to launch the kernel in a container used by the provided username.

```{admonition} Important!
:class: warning
When using kerberos in a YARN managed cluster, the server's user needs to be set up as a
`proxyuser` superuser in Hadoop configuration. Please refer to the
[Hadoop documentation](https://hadoop.apache.org/docs/current/hadoop-project-dist/hadoop-common/Superusers.html)
regarding the proper configuration steps.
```

### SPNEGO Authentication to YARN APIs

When kerberos is enabled in a YARN managed cluster, the administration UIs can be configured to
require authentication/authorization via SPNEGO. When running kernels in an environment configured
this way, we need to convey an extra configuration to enable the proper authorization when
communicating with YARN via the YARN APIs.

`GP_YARN_ENDPOINT_SECURITY_ENABLED` indicates the requirement to use SPNEGO authentication/authorization
when connecting with the YARN APIs and can also be conveyed via the boolean configuration option
`c.YarnProvisioner.yarn_endpoint_security_enabled` (default = False)

### Impersonation in Standalone or YARN Client Mode

Impersonation performed in standalone or YARN client modes (via the `DistributedProvisioner`) tends
to take the form of using `sudo` to perform the kernel launch as the target user. This can also be
configured within the [run.sh](https://github.com/jupyter-server/enterprise_gateway/blob/main/etc/kernelspecs/spark_python_yarn_client/bin/run.sh)
script and requires the following:

1. The server's user (i.e., the user in which hosting server is running) must be enabled to perform
   sudo operations on each potential host. This enablement must also be done to prevent password
   prompts since the server runs in the background. Refer to your operating system documentation
   for details.
1. Each user identified by `KERNEL_USERNAME` must be associated with an actual operating system
   user on each host.
1. Once the server's user is configured for `sudo` privileges it is **strongly recommended** that
   that user be included in the set of `unauthorized_users`. Otherwise, kernels not configured
   for impersonation, or those requests that do not include `KERNEL_USERNAME`, will run as
   the, now, highly privileged user in which the server is running!

```{warning}
Should impersonation be disabled after granting the server's user elevated privileges, it is
**strongly recommended** those privileges be revoked (on all hosts) prior to starting kernels
since those kernels will run as the gateway user **regardless of the value of KERNEL_USERNAME**.
```

## SSH Tunneling

Gateway Provisioners can be configured to perform SSH tunneling on the five ZeroMQ kernel sockets
as well as the communication socket created within the launcher and used to perform remote and
cross-user signalling functionality. SSH tunneling is NOT enabled by default. Tunneling can be
enabled/disabled via the environment variable `GP_ENABLE_TUNNELING=False`. Note, there is no
configuration file support for this variable.

Note that SSH by default validates host keys before connecting to remote hosts and the connection
will fail for invalid or unknown hosts. Gateway Provisioners honors this requirement, and invalid
or unknown hosts will cause tunneling to fail. Please perform necessary steps to validate all
hosts before enabling SSH tunneling, such as:

- SSH to each node cluster and accept the host key properly
- Configure SSH to disable `StrictHostKeyChecking`

## Using Generic Security Service (Kerberos)

Gateway Provisioners has support for SSH connections using GSS (for example Kerberos), which
enables its deployment without the use of an ssh key. The `GP_REMOTE_GSS_SSH` environment
variable can be used to control this behavior.

```{seealso}
The list of [additional supported environment variables](config-add-env.md#additional-environment-variables).
```
