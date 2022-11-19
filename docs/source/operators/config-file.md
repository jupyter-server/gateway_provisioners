# Configuration file options

Because Remote Provisioners leverage the `traitlets` package, configurable options can be defined
within the Jupyter-based application's configuration file - since it too will leverage `traitlets`.

FIXME

Here's an example entry. Note that its default value, when defined, is also displayed, along with
the corresponding environment variable name:

```python
## Bracketed comma-separated list of hosts on which DistributedProcessProxy
#  kernels will be launched e.g., ['host1','host2'].
#  (EG_REMOTE_HOSTS env var - non-bracketed, just comma-separated)
#  Default: ['localhost']
# c.RemoteProvisionerConfigMixin.remote_hosts = ['localhost']
```
