# Installing Remote Provisioners

Remote Provisioners require `jupyter_client >= 7.0`. Attempts to install into existing environments
with older versions of `jupyter_client` will be met with resolution warnings and no kernel provisioners
(remote or local) will be used.

```{warning}
Enterprise Gateway is currently incompatible with `jupyter_client >= 7.0`.  As a result, you
should **not** install Enterprise Gateway into the same Python environment in which you intend
to use kernel provisioners.
```

FIXME talk about the optional installs [k8s] [docker] [yarn]

```bash
# install using pip from pypi
pip install --upgrade remote_provisioners
```

```bash
# install using conda from conda forge
conda install -c conda-forge remote_provisioners
```

At this point, the Remote Provisioner deployment provides the _ability_ to configure kernel specifications for any of its
kernel provisioner implementations.

To uninstall Remote Provisioners...

```bash
#uninstall using pip
pip uninstall remote_provisioners
```

```bash
#uninstall using conda
conda uninstall remote_provisioners
```

```{tip}
To fully _complete_ the removal of remote provisioners, any kernel specifications derived from `RemoteProvisioner`
should be removed as well.
```
