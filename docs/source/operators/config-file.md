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
c.DistributedProvisioner.remote_hosts = ['localhost']
```

FIXME - Include the various options broken down by common, then each provisioner...
