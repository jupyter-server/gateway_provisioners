# Per-kernel overrides

As mentioned in the overview of [Gateway Provisioner Configuration](../contributors/system-architecture.md#gateway-provisioners-configuration)
capabilities, it's possible to override or amend specific system-level configuration values on a
per-kernel basis. These capabilities can be implemented with the kernel specification's
kernel_provisioner's `config` stanza or via environment variables.

## Per-kernel configuration overrides

The following enumerates the set of per-kernel configuration overrides:

```{note}
Unless noted otherwise, these values only apply to provisioners derived from `RemoteProvisioner`.
```

### `RemoteProvisioner` per-kernel overrides

- `authorized_users`: This provisioner configuration entry can be used to override
  `c.RemoteProvisionerConfigMixin.authorized_users`. Any values specified in the config
  dictionary override the globally defined values. Note that the typical use-case for
  this value is to not set `c.RemoteProvisionerConfigMixin.authorized_users` at the global level,
  but then restrict access at the kernel level.
- `unauthorized_users`: This provisioner configuration entry can be used to **_amend_**
  `c.RemoteProvisionerConfigMixin.unauthorized_users`. Any values specified in the config dictionary
  are **added** to the globally defined values. As a result, once a user is denied access at the
  global level, they will _always be denied access at the kernel level_.
- `port_range`: This remote provisioner configuration entry can be used to override
  `c.RemoteProvisionerConfigMixin.port_range`. Any values specified in the config
  dictionary override the globally defined values.

### `DistributedProvisioner` per-kernel overrides

- `remote_hosts`: This provisioner configuration entry can be used to override
  `c.DistributedProvisioner.remote_hosts`. Any values specified in the config dictionary
  override the globally defined values.

### `YarnProvisioner` per-kernel overrides

- `yarn_endpoint`: This provisioner configuration entry can be used to override
  `c.RemoteProvisionerConfigMixin.yarn_endpoint`.
  Any values specified in the config dictionary override the globally defined values. These
  apply to all `YarnProvisioner` kernels. Note that you'll likely be required to specify a
  different `HADOOP_CONF_DIR` setting in the kernel.json's `env` stanza in order for the
  `spark-submit` command to target the appropriate YARN cluster.

## Per-kernel environment overrides

In some cases, it is useful to allow specific values that exist in a kernel.json `env` stanza to be
overridden on a per-kernel basis. For example, if the kernel.json supports resource limitations you
may want to allow some requests to have access to more memory or GPUs than another. Gateway Provisioners
enables this capability by honoring environment variables provided in the json request over
those same-named variables in the kernel.json `env` stanza.

Environment variables for which this can occur are any variables prefixed with `KERNEL_`.

See [Kernel Environment Variables](../users/kernel-envs.md) in the Users Guide
for a complete set of recognized `KERNEL_` variables.
