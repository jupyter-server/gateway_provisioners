# Application Support

Welcome to Gateway Provisioner's application support page.  Here, we document helpful
approaches for how to deploy _applications_ that utilize Gateway Provisioners.

This information is primarily suited to container-based environments (e.g., Docker &
Kubernetes) since deployment into those environments usually require additional steps.

The following will illustrate how to deploy two different applications into these environments:
Jupyter Kernel Gateway and Jupyter Lab.

See our [Operators Guide](https://gateway-provisioners.readthedocs.io/en/latest/operators/index.html) for additional deployment information.

## Deployment into Docker Environments

Deployment into Docker environments requires the application be configured into a docker image.

The Dockerfile located in docker/Dockerfile contains a multi-stage build that:

1. Determines from where the gateway_provisioners package will be derived (release or local)
1. Includes the desired application (Kernel Gateway or Lab)
1. Generates the applicable kernel specifications for Docker, DockerSwarm,and Kubernetes environments
1. Filters the allowed kernel specifications to only the Docker-based kernel specifications
   (See next section for filtering Kubernetes-specific kernel specifications)
1. Adds a `start-application.sh` script to launch the desired application

### Building Application Images

Support for building application images is built into the `Makefile`.  The following targets
apply to application builds:

#### `app-images`

Use `make app-images` to build two images `elyra/gp-jkg:dev` and `elyra/gp-lab:dev` containing
Jupyter Kernel Gateway and Jupyter Lab, respectively.

#### `gp-jkg`

Use `make gp-jkg` to build only `elyra/gp-jkg:dev` containing Jupyter Kernel Gateway.

#### `gp-lab`

Use `make gp-lab` to build only `elyra/gp-lab:dev` containing Jupyter Lab.

#### `clean-app-images`

Use `make clean-app-images` to remove BOTH `elyra/gp-jkg:dev` and `elyra/gp-lab:dev`.  Individual
images can be cleaned using either `make clean-gp-jkg` or `make clean-gp-lab`.

#### `push-app-images`

Use `make push-app-images` to push BOTH `elyra/gp-jkg:dev` and `elyra/gp-lab:dev` to dockerhub.  Individual
images can be pushed using either `make push-gp-jkg` or `make push-gp-lab`.

#### Available Adjustments

As with [kernel images](https://gateway-provisioners.readthedocs.io/en/latest/operators/installing-kernels-container.html#kernel-image-dockerfiles)
there are build arguments that can be specified in the `make` command that influence how the image is built.

##### `BASE_CONTAINER`

`BASE_CONTAINER` can be specified to override the base container upon which the application is built.  By
default, the application images are built upon `elyra/gp-spark-base` since they will require Spark.

##### `PACKAGE_SOURCE`

`PACKAGE_SOURCE` supports two values `release` and `local`.  A value of `release` indicates that
the gateway_provisioners package be installed from PyPi.org using `pip` - thereby installing the
latest release.  While a value of `local` indicates that the local wheel distribution be installed.

##### `SERVER_APP`

`SERVER_APP` can take one of two values (`jkg` or `lab`) to identify which application should be installed
and invoked.  A value of `jkg` indicates that `jupyter-kernel-gateway` be installed and `jupyter-kernelgateway`
be invoked with a display name of `Jupyter Kernel Gateway`.  While a value of `lab` indicates that `jupyterlab`
be installed and `jupyter-lab` be invoked with a display name of `Jupyter Lab`.

##### `DOCKER_ORG`

`DOCKER_ORG` can be specified to determine the docker organization.  The default value is `elyra`.

##### `TAG`

`TAG` can be specified to determine the tag to apply to the image.  The default is `dev` when the
Gateway Provisioners version indicates a development version cycle (e.g., `0.2.0.dev0`) or the
actual version value if the there is no `devN` suffix.

## Deployment into Kubernetes Environments

Deployment into Kubernetes environments first requires the application reside within a docker image (see above).
Once an image exists, deployment consists of updating the `values.yaml` file and deploying the helm chart.

Much of the information (like environment variables) in the docker image can be overridden
in the helm chart.  For example, the list of allowed kernelspecs is specified in the `Dockerfile`
via the `APP_ALLOWED_KERNELS` environment variable and reflects the _docker-based_ kernel specifications.
However, the `APP_ALLOWED_KERNELS` in the helm charts will be overridden to reflect the _kubernetes-based_
kernel specifications.

The primary portion of [`values.yaml`](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/app-support/kubernetes/helm/gateway-provisioners/values.yaml)
that applies to application-specific information is in the `application` stanza.  Here, things
like the application name, command, and image can be specified, in addition to the allowed
kernels and culling intervals, etc.

Other values that are more applicable to the _application_ rather than the _kernel_ are located
in the `provisioner` stanza.  These are values that are used by Gateway Provisioners _within_
the application.

### Deploying Kubernetes Applications

Once the appropriate values within the `values.yaml` file have been updated, the application
is ready to deploy.

First, create the namespace in which the application should reside. We use `gateway-provisioners` but
that value is up to you:

```bash
kubectl create namespace gateway-provisioners
```

Next, you are ready to deploy the application.  From the repo's root, issue the following (note:
we're using a deployment name of `gateway-provisioners`:

```bash
helm  upgrade --install  gateway-provisioners gateway_provisioners/app-support/kubernetes/helm/gateway-provisioners -n gateway-provisioners
```

To remove the deployment, issue:

```bash
helm delete gateway-provisioners -n gateway-provisioners
```
