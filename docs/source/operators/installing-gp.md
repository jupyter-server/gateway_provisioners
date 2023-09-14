# Installing Gateway Provisioners (Servers)

These instructions are relative to the host application _server_.  For _container-based_ installations, see
[Installing Gateway Provisioners (Containers)](installing-gp-container.md).

```{attention}
Gateway Provisioners require `jupyter_client >= 7.0`. Attempts to install Gateway Provisioners into existing environments
with older versions of `jupyter_client` will be met with resolution warnings and no kernel provisioners
(remote or local) will be used.
```

Base functionality is installed using either of the following commands...

```bash
pip install --upgrade gateway_provisioners
```

or

```bash
mamba install -c conda-forge gateway_provisioners
```

```{note}
We recommend the use of `mamba` over `conda`.  However, if you need to use `conda`, all `mamba`
commands should be directly replaceable with `conda`.
```

## Optional Dependencies

At this point, the Gateway Provisioners provides the _ability_ to configure kernel specifications for any of its
kernel provisioner implementations. However, because multiple target configurations are supported, the
libraries relative to the actual target environment should also be installed using optional dependencies.

```{note}
Attempts to create kernel specifications for environments in which the optional dependencies have not been installed
will still generate specifications, but warning messages will also be produced as those specifications are not
usable until their dependencies have been installed.
```

GatewayProvisioners supports the following optional dependencies, each of which can be included in brackets on
the installation command.

### Hadoop YARN

If you plan to target Hadoop YARN environments use:

```bash
pip install --upgrade gateway_provisioners[yarn]
```

or

```bash
mamba install -c conda-forge gateway_provisioners[yarn]
```

### Distributed/SSH

If you plan to target multi-node environments via SSH, nothing additional is necessary as all required libraries
are included in the base installation.

```bash
pip install --upgrade gateway_provisioners
```

or

```bash
mamba install -c conda-forge gateway_provisioners
```

## Uninstalling Gateway Provisioners

To uninstall Gateway Provisioners...

```bash
pip uninstall gateway_provisioners
```

```bash
mamba uninstall gateway_provisioners
```

```{tip}
To fully _complete_ the removal of gateway provisioners, any kernel specifications referencing the various
Gateway Provisioners should be removed as well.  Kernel specifications can be located using `jupyter kernelspec list`.
```
