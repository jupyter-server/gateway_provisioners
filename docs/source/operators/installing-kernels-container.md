# Installing Supported Kernels (Containers)

Gateway Provisioners includes tooling to generate kernel specifications that support the following kernels:

- IPython kernel (Python)
- Apache Toree (Scala)
- IRKernel (R)

Kernel specifications reside within the host application image (or volume mount) and their generation is addressed
in the applicable sections for [Kubernetes](deploy-kubernetes.md) and [Docker/DockerSwarm](deploy-docker.md).  What
follows are instructions for how to build the kernel-based image.

```{tip}
Gateway Provisioners provides a [Makefile](https://github.com/jupyter-server/gateway_provisioners/blob/main/Makefile)
for building the various kernel images.  The instructions that follow will reference `make` targets to accomplish
these tasks.
```

## Kernel-image Dockerfiles

There are two forms of kernel images that can be created, one for regular or _vanilla_ kernels, another
for Spark-based kernels.  Both use the same Dockerfile, but Spark-based images will specify a different base image
from which the target image is derived.

### Spark Base Image

Spark-based images will be built upon the `elyra/gp-spark-base` image, whose
[`Dockerfile`](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/docker/gp-spark-base/Dockerfile) is located in
[`gateway_provisioners/docker/gp-spark-base`](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/docker/gp-spark-base).
This image builds on `jupyter/docker-stacks-foundation:2022-11-15` by installing Spark.  However, that base can also be
substituted via the build argument `BASE_CONTAINER`.

To build the spark base image use:

```bash
make gp-spark-base
```

This will create an image named, by default, `elyra/gp-spark-base:dev`.  The organization (`elyra`) and tag (`dev`) can
be controlled using variables `DOCKER_ORG` and `TAG`, respectively.  For example, to create a `gp-spark-base` image
with a custom organization and tag of the form `my-custom-org/gp-spark-base:my-custom-tag`, you can use:

```bash
make DOCKER_ORG=my-custom-org TAG=my-custom-tag gp-spark-base
```

Other arguments that can be specified are `SPARK_VERSION` (default is `3.3.1`), `HADOOP_VERSION` (`2`), `SCALA_VERSION`
(`2.12`), `OPENJDK_VERSION` (`17`), and `SPARK_CHECKSUM` (depends on `SPARK_VERSION`).

```{tip}
As with `DOCKER_ORG` and `TAG`, each of the above build arguments can be specified on the `make` command.
```

### Kernel Images

The [`Dockerfile`](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/docker/kernel-image/Dockerfile)
used to create a kernel image representing any of the supported kernels is located in
[`gateway_provisioners/docker/kernel-image`](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/docker/kernel-image).

This is a [_multi-stage build_](https://docs.docker.com/build/building/multi-stage/) Dockerfile whose build options are
driven by [`docker build` arguments](https://docs.docker.com/engine/reference/builder/#arg).  There are three primary
arguments that drive a kernel's image build, `BASE_CONTAINER`, `KERNEL_LANG`, and `PACKAGE_SOURCE`.

#### `BASE_CONTAINER`

Using a `BASE_CONTAINER` build argument (e.g., `--build-arg BASE_CONTAINER=xxx`) controls from which image the kernel
image will be derived.  By default, _vanilla_ kernel images are derived from `jupyter/docker-stacks-foundation:2022-11-15`
while _spark-based_ kernel images should specify a `BASE_CONTAINER` of either `elyra/gp-spark-base:dev` or another applicable image.

Gateway Provisioner's `Makefile` supports targets for three spark-based images: `gp-kernel-spark-py`,
`gp-kernel-spark-r`, and `gp-kernel-scala`, and two _vanilla_ kernel images: `gp-kernel-py` and `gp-kernel-r`.
As with the spark base image, the `DOCKER_ORG` and `TAG` can be similarly
controlled, but by default, the following command will produce images names `elyra/gp-kernel-spark-py:dev`,
`elyra/gp-kernel-spark-r:dev`, `elyra/gp-kernel-scala:dev`, `elyra/gp-kernel-py:dev`,
and `elyra/gp-kernel-r:dev`:

```bash
make gp-kernel-spark-py gp-kernel-spark-r gp-kernel-scala gp-kernel-py gp-kernel-r
```

```{attention}
The Scala kernel (based on Apache Toree) is predicated on its use within a Spark environment, so a _vanilla_ version
of the Scala kernel is not provided.
```

```{tip}
The _helper-target_ `kernel-images` can be used to create all five kernel images via `make kernel-images`.
```

#### `KERNEL_LANG`

The second primary build argument to consider is the kernel language. Each of the previously mentioned Makefile targets
automatically set `--build-arg KERNEL_LANG=<lang>` to the expected argument.  If not specified, `KERNEL_LANG` defaults
to `python`.  `KERNEL_LANG` must be one of the following values: `python`, `r`, or `scala`.

It is this build argument that determines which kernel package to install, all of which is handled in the `Dockerfile`.

The resulting image will include an `ENV` entry of `KERNEL_LANGUAGE` with one of the respective values: `Python`, `R`,
or `Scala`, as well as a `LABEL` entry of `KERNEL_LANG` with the respective lowercase form: `python`, `r`, or `scala`.

#### `PACKAGE_SOURCE`

The third primary build argument is `PACKAGE_SOURCE`.  This identifies from where the Gateway Provisioners installation
should come.  By default, `PACKAGE_SOURCE=release`, meaning that the Gateway Provisioners package will be installed
from the latest release.  If a build argument for `PACKAGE_SOURCE` specifies `local`, then the
locally built wheel file for Gateway Provisioners will be installed.  This option is ideal for development environments.

Because the `Makefile` is _plumbed_ for `PACKAGE_SOURCE`, it can be specified directly in the `make` command.  For example,
the following will build a vanilla kernel for python using a locally built wheel file:

```bash
make PACKAGE_SOURCE=local gp-kernel-py
```

The resulting image will include a `LABEL` entry of `PACKAGE_SOURCE` with one of the respective values: `release` or
`local`.

### Bootstrapping the Kernel Image

One of the more important tasks performed by `kernel-image/Dockerfile` is the installation of the bootstrap script.
This script becomes the image's command (`CMD`) and is placed into the image using the `jupyter image-bootstrap install`
command line script.

```dockerfile
CMD /usr/local/bin/bootstrap-kernel.sh

# Install bootstrap and applicable launchers (per languages)
RUN jupyter image-bootstrap install --languages ${KERNEL_LANG}

RUN chown jovyan:users /usr/local/bin/bootstrap-kernel.sh && \
	chmod 0755 /usr/local/bin/bootstrap-kernel.sh && \
	chown -R jovyan:users /usr/local/bin/kernel-launchers
```

Upon its installation, the `CMD` is set into the image and the necessary kernel-launcher scripts are placed into
`/usr/local/bin/kernel-launchers`.
