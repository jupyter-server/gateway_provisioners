# Custom Kernel Images

This section presents information needed for how a custom kernel image could be built for your own
uses with Gateway Provisioners. This is typically necessary if one desires to extend the existing
image with additional supporting libraries or an image that encapsulates a different set of functionality altogether.

## Extending Existing Kernel Images

A common form of customization occurs when the existing kernel image is serving the fundamentals but
the user wishes to extend the image with additional libraries to prevent the need to install them during
the Notebook's execution. Since the image already meets the
[basic requirements](#requirements-for-custom-kernel-images), this is really just a matter of referencing the
existing image in the `FROM` statement and installing additional libraries. Because the kernel images
produced by Gateway Provisioners do not run as the `root` user, you may need to switch users to perform the update.

```dockerfile
FROM elyra/kernel-py:VERSION

USER root  # switch to root user to perform installation (if necessary)

RUN pip install my-libraries

USER $NB_UID  # switch back to the jovyan user
```

## Bringing Your Own Kernel Image

Users that do not wish to extend an existing kernel image must be cognizant of a couple of things.

1. Requirements of a kernel-based image to be used by Gateway Provisioners.
1. Is the base image one from [Jupyter Docker-stacks](https://github.com/jupyter/docker-stacks)?

### Requirements for Custom Kernel Images

Custom kernel images require some support files for integrating with Gateway Provisioners, a bootstrap file that
receives information when the container is started, and a set of kernel launchers for whichever kernels the image
needs to support.

#### Bootstrap-kernel.sh

Gateway Provisioners provides a single [bootstrap-kernel.sh](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/kernel-launchers/bootstrap/bootstrap-kernel.sh)
script that handles the three kernel languages supported out of the box - Python, R, and Scala. When a kernel image
is started by Gateway Provisioners, parameters used within the `bootstrap-kernel.sh` script are conveyed via environment
variables. The bootstrap script is then responsible for validating and converting those parameters to meaningful
arguments to the appropriate launcher.

#### Kernel Launcher

The kernel launcher, as discussed [here](kernel-launcher.md), does a number of things. In particular, it creates
the connection ports and conveys that connection information back to the host application via the socket identified
by the response address parameter. Although not a requirement for container-based usage, it is recommended that the
launcher be written in the same language as the kernel. (This is more of a requirement when used in applications
like Hadoop YARN.)

Both of these sets of files can be included into a custom kernel image using the following `Dockerfile` snippet:

```dockerfile
# Install remote provisioners from PYPI
RUN pip install gateway_provisioners

CMD /usr/local/bin/bootstrap-kernel.sh

# Install bootstrap and applicable launchers (per languages)
RUN jupyter image-bootstrap install --languages python --languages r

RUN chown jovyan:users /usr/local/bin/bootstrap-kernel.sh && \
	chmod 0755 /usr/local/bin/bootstrap-kernel.sh && \
	chown -R jovyan:users /usr/local/bin/kernel-launchers
```

When invoking the `jupyter image-bootstrap install` command, the following output will occur:

```text
[ImageBootstrapInstaller] Kernel-launcher files have been copied to /usr/local/bin/kernel-launchers for the following languages: ['python', 'r'].
[ImageBootstrapInstaller] bootstrap-kernel.sh has been copied to /usr/local/bin.
[ImageBootstrapInstaller] The CMD entry in the Dockerfile should be updated to: CMD /usr/local/bin/bootstrap-kernel.sh
```

### About Jupyter Docker-stacks Images

Most of what is presented assumes the base image for your custom image is derived from the
[Jupyter Docker-stacks](https://github.com/jupyter/docker-stacks) repository. As a result, it's good to cover what
makes up those assumptions so you can build your own image independently of the docker-stacks repository.

All images produced from the docker-stacks repository come with a certain user configured. This user is named
`jovyan` and is mapped to a user id (UID) of `1000` and a group id (GID) of `100` - named `users`.

The various startup scripts and commands typically reside in `/usr/local/bin` and we recommend trying to
adhere to that policy.

The base Jupyter image, upon which most all images from docker-stacks are built, also contains a `fix-permissions`
script that is responsible for _gracefully_ adjusting permissions based on its given parameters. By only changing
the necessary permissions, use of this script minimizes the size of the docker layer in which that command is invoked
during the build of the docker image.

```{tip}
All kernel images produced by Gateway Provisioners derive from `jupyter/docker-stacks-foundation` - which is the root
image for all docker-stacks images.  You can see how our kernel images are built looking at
[`kernel-image/Dockerfile`](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/docker/kernel-image/Dockerfile).
```

## Deploying Your Custom Kernel Image

The final step in deploying a customer kernel image is generating a corresponding kernel specifications directory
that is available to the host application. Since the host application is also running in a container, its import that
its kernel specifications directory either be mounted externally or a new host application image is created with
the appropriate directory in place. For the purposes of this discussion, we'll assume the kernel specifications
directory, `/usr/local/share/jupyter/kernels`, is externally mounted.

Depending on the environment, Kubernetes or Docker, you can use with `jupyter-k8s-spec` or `jupyter-docker-spec`,
respectively.  Invoke the appropriate script by adding the `--image-name` parameter identifying the name of your
custom kernel image.  For example, if your custom image is named `acme/data-sci-py:2.0` and you are targeting
Kubernetes, issue:

```dockerfile
RUN jupyter k8s-spec install --image-name acme/data-sci-py:2.0 --kernel-name data_sci_py --display-name 'Data Science 2.0'
```

which will produce a `kernel.json` file in `/usr/local/share/jupyter/kernels/data_sci_py` containing the following:

```json
{
  "argv": [
    "python",
    "/usr/local/share/jupyter/kernels/data_sci_py/scripts/launch_kubernetes.py",
    "--kernel-id",
    "{kernel_id}",
    "--port-range",
    "{port_range}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--kernel-class-name",
    "ipykernel.ipkernel.IPythonKernel"
  ],
  "env": {},
  "display_name": "Data Science 2.0",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "debugger": true,
    "kernel_provisioner": {
      "provisioner_name": "kubernetes-provisioner",
      "config": {
        "image_name": "acme/data-sci-py:2.0",
        "launch_timeout": 30
      }
    }
  }
}
```
