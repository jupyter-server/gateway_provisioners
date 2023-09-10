# Installing Gateway Provisioners (Containers)

These instructions are relative to the host application _image_.  For configuring kernel images for use with Gateway
Provisioners see [Installing Supported Kernels (Containers)](installing-kernels-container.md).  For instructions on installing
Gateway Provisioners on host application _servers_, please see [Installing Gateway Provisioners (Servers)](installing-gp.md).

```{attention}
Gateway Provisioners require `jupyter_client >= 7.0`. Attempts to install Gateway Provisioners into existing environments
with older versions of `jupyter_client` will be met with resolution warnings and no kernel provisioners
(remote or local) will be used.
```

Gateway Provisioners provides the _ability_ to configure kernel specifications for any of its
kernel provisioner implementations. However, because these instructions are relative to containers that are typically
built with specific environments in mind, it's important to include the desired optional dependency for either
Kubernetes or Docker environments.

```{note}
We recommend the use of `mamba` over `conda`.  However, if you need to use `conda`, all `mamba`
commands should be directly replaceable with `conda`.
```

## Kubernetes

If you plan to target Kubernetes environments you will likely issue either of the following commands
from within the `Dockerfile` corresponding to the hosting application's docker image:

```dockerfile
RUN pip install --upgrade gateway_provisioners[k8s]
```

or

```dockerfile
RUN mamba install -c conda-forge gateway_provisioners[k8s]
```

## Docker or DockerSwarm

If you plan to target Docker or DockerSwarm environments you will likely issue either of the
following commands from within the `Dockerfile` corresponding to the hosting application's docker image:

```dockerfile
RUN pip install --upgrade gateway_provisioners[docker]
```

or

```dockerfile
RUN mamba install -c conda-forge gateway_provisioners[docker]
```

## Mixed Environments

If you are unsure in which environment this image will be used, you can install both Kubernetes and Docker client
libraries.  In addition, in some cases, you may wish to support Yarn from within a Kubernetes or Docker cluster, in
which case, you may even wish to add its client libraries as well:

```dockerfile
RUN pip install --upgrade gateway_provisioners[k8s,docker,yarn]
```
