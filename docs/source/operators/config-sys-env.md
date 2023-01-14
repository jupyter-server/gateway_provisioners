# System-owned environment variables

The following environment variables are used by Gateway Provisioners and listed here
for completeness.

```{warning}
Manually setting these variables could adversely affect operations.
```

```text
  GP_DOCKER_MODE
    Docker only.  Used by launch_docker.py to determine if the kernel container
    should be created using the swarm service API or the regular docker container
    API.  The applicable docker-based provisioner sets this value depending on
    whether the kernel is using the DockerSwarmProvisioner or DockerProvisioner.

  GP_RESPONSE_ADDRESS
    This value is set during each kernel launch and resides in the environment of
    the kernel launch process. Its value represents the address to which the remote
    kernel's connection information should be sent.  Gateway Provisioner's `ResponseManager`
    is listening on that socket and will associate that connection information with
    the responding kernel.
```
