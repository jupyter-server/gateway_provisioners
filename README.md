# Gateway Provisioners

[![Build Status](https://github.com/gateway-experiments/gateway_provisioners/actions/workflows/build.yml/badge.svg?query=branch%3Amain++)](https://github.com/gateway-experiments/gateway_provisioners/actions/workflows/build.yml/badge.svg?query=branch%3Amain++)
[![Documentation Status](https://readthedocs.org/projects/gateway_provisioners/badge/?version=latest)](https://gateway-provisioners.readthedocs.io/en/latest/?badge=latest)

**NOTE: This repository is experimental and undergoing frequent changes!**

Gateway Provisioners provides [kernel provisioners](https://jupyter-client.readthedocs.io/en/latest/provisioning.html)
that interact with kernels launched into resource-managed clusters or otherwise run remotely from the launching server.
This functionality derives from [Jupyter Enterprise Gateway's](https://github.com/jupyter-server/enterprise_gateway)
_process proxy_ architecture. However, unlike \[process proxies\]
(https://jupyter-enterprise-gateway.readthedocs.io/en/latest/contributors/system-architecture.html#process-proxy),
you do not need to use a gateway server to use these provisioners - although, in certain cases,
it is recommended (for example when the launching server does not reside within the same network as the launched kernel).

Here is the current set of provisioners provided by this package, many of which have their requirements conditionally
installed:

- `KubernetesProvisioner` - Kernels (residing in images) are launched as pods within a Kubernetes cluster
  - `pip install gateway_provisioners[k8s]`
- `DockerSwarmProvisioner` - Kernels (residing in images) are launched as containers within a DockerSwarm cluster
- `DockerProvisioner` - Kernels (residing in images) are launched as containers
  - `pip install gateway_provisioners[docker]`
- `YarnProvisioner` - Kernels are launched into a Hadoop YARN cluster (primarily Spark)
  - `pip install gateway_provisioners[yarn]`
- `DistributedProvisioner` - Kernels are launched across a set of hosts using SSH, round-robin
  - `pip install gateway_provisioners`

This package also includes command-line utilities that can be used to create kernel specifications or inject bootstrap
files into docker images relative to the desired provisioner:

- `jupyter-k8s-spec` - for building kernel specifications relative to the `KubernetesProvisioner`
- `jupyter-docker-spec` - for building kernel specifications relative to `DockerProvisioner` and `DockerSwarmProvisioner`
- `jupyter-yarn-spec` - for building kernel specifications relative to the `YarnProvisioner`
- `jupyter-ssh-spec` - for building kernel specifications relative to the `DistributedProvisioner`
- `jupyter-image-bootstrap` - for injecting bootstrap support when building kernel-based images

**NOTE: The container-based provisioners (`KubernetesProvisioner`, `DockerSwarmProvisioner`, and `DockerProvisioner`)
require that the hosting server also be running within the same environment/network. As a result, these
provisioners may be better suited for use by a Gateway Server (Kernel Gateway or Enterprise Gateway) so
as to not require the Notebook/Lab server to be in a container.**

## Installation

Detailed installation instructions are located in the
[Operators Guide](https://gateway-provisioners.readthedocs.io/en/latest/operators/installing-gp.html)
of the project docs. Here's a quick start using `pip`:

```bash
# install from pypi
pip install --upgrade gateway-provisioners

# options for the command-line utilities can be viewed using '--help-all'
jupyter k8s-spec install --help-all

# run it with default options
jupyter k8s-spec install
```

## Contributing

The [Contribution page](https://gateway-provisioners.readthedocs.io/en/latest/contributors/contrib.html) includes
information about how to contribute to Gateway Provisioners. We encourage you to explore the other topics in our \[Contributor's Guide\]
(https://gateway-provisioners.readthedocs.io/en/latest/contributors/index.html)
like how to [set up a development environment](https://gateway-provisioners.readthedocs.io/en/latest/contributors/devinstall.html),
gaining an understanding of the [system architecture](https://gateway-provisioners.readthedocs.io/en/latest/contributors/system-architecture.html),
and taking a look at the \[API documentation\[(https://gateway-provisioners.readthedocs.io/en/latest/api/modules.html), among other thigns.
