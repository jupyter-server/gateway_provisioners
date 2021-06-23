# Remote Provisioners

__NOTE: This repository is experimental and undergoing frequent changes!__

The RemoteProvisioners package provides the following kernel provisioners:

- YarnProvisioner - Kernels are launched into a Hadoop YARN cluster (primarily Spark)
- DistributedProvisioner - Kernels are launched across a set of hosts using SSH, round-robin
- KubernetesProvisioner - Kernels (residing in images) are launched within a Kubernetes cluster
- DockerSwarmProvisioner - Kernels (residing in images) are launched within a DockerSwarm cluster
- DockerProvisioner - Kernels (residing in images) are launched as Docker containers (from a Docker container)


Note: The container-based provisoners (KubernetesProvisioner, DockerSwarmProvisioner and DockerProvisioner)
require that the hosting server also be running within the same environment/network.  As a result, these
provisioners may be better suited for use by a Gateway Server (Kernel Gateway or Enterprise Gateway) so
as to not require the Notebook/Lab server to be in a container.
