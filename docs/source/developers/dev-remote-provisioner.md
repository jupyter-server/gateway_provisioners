# Implementing a Gateway Provisioner

A gateway provisioner implementation is necessary if you want to interact with a resource manager that is not
currently supported or extend some existing behaviors. Examples of resource managers in which there's been interest
include [Slurm Workload Manager](https://slurm.schedmd.com/documentation.html) and
[Apache Mesos](https://mesos.apache.org/), for example. In the end, it's really a matter of having access to
an API and the ability to apply "tags" or "labels" in order to _discover_ where the kernel is running within
the managed cluster. Once you have that information, then it becomes a matter of implementing the appropriate
methods to control the kernel's lifecycle.

## General Approach

Please refer to the [Gateway Provisioners section](../contributors/system-architecture.md#gateway-provisioners) in the
System Architecture pages for descriptions and structure of existing gateway provisioners. Here is the general
guideline for the process of implementing a gateway provisioner.

1. Identify and understand how to _decorate_ your "job" within the resource manager. For example,
   1. In Hadoop YARN, this is done by
      using the kernel's ID as the _application name_ by setting the
      [`--name` parameter to `${KERNEL_ID}`](https://github.com/jupyter-server/enterprise_gateway/blob/54c8e31d9b17418f35454b49db691d2ce5643c22/etc/kernelspecs/spark_python_yarn_cluster/kernel.json#L14).
   1. In Kubernetes, we apply the kernel's ID to the [`kernel-id` label on the POD](https://github.com/jupyter-server/enterprise_gateway/blob/54c8e31d9b17418f35454b49db691d2ce5643c22/etc/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2#L16).
1. Today, all invocations of kernels into resource managers use a shell or python script mechanism configured into the
   `argv` stanza of the kernelspec. If you take this approach, you need to apply the necessary changes to integrate
   with your resource manager.
1. Determine how to interact with the resource manager's API to _discover_ the kernel and determine on which
   host it's running. This interaction should occur immediately following receipt of the kernel's connection
   information in its response from the kernel launcher. This extra step, performed within `confirm_remote_startup()`,
   is necessary to get the appropriate host name as reflected in the resource manager's API.
1. Determine how to monitor the "job" using the resource manager API. This will become part of the `poll()`
   implementation to determine if the kernel is still running. This should be as quick as possible since it occurs
   every 3 seconds. If this is an expensive call, you may need to make some adjustments like skip the call every so often.
1. Determine how to terminate "jobs" using the resource manager API. This will become part of the kernel's termination
   sequence, but probably only necessary if the message-based shutdown does not work (i.e., a last resort).

```{tip}
Because kernel IDs are globally unique, they serve as ideal identifiers for discovering where in the cluster the kernel
is running and are recommended "keys".
```

You will likely need to provide implementations for `launch_process()`, `poll()`, `wait()`, `send_signal()`, and
`kill()`, although, depending on where your provisioner resides in the class hierarchy, some implementations may be
reused.

For example, if your provisioner is going to service remote kernels, you should consider deriving your implementation
from the [`RemoteProvisionerBase` class](https://github.com/jupyter-server/gateway_provisioners/blob/9de8af8a361aa779f8eb4d10585c0d917bb3731f/gateway_provisioners/remote_provisioner.py#L75).
If this is the case, then you'll need to implement `confirm_remote_startup()`.

Likewise, if your process proxy is based on containers, you should consider deriving your implementation from
the [`ContainerProvisionerBase` class](https://github.com/jupyter-server/gateway_provisioners/blob/9de8af8a361aa779f8eb4d10585c0d917bb3731f/gateway_provisioners/container.py#L32).
If this is the case, then you'll need to implement `get_container_status()` and `terminate_container_resources()`
rather than `confirm_remote_startup()`, etc.

Once the gateway provisioner has been implemented, construct an appropriate kernel specification that references your
gateway provisioner and iterate until you are satisfied with how your remote kernels behave.

If you intend to contribute your gateway provisioner into this package, you can extend the CLI tooling to create
applicable kernel specifications and launch scripts.
