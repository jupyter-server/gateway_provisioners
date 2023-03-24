# Implementing a Kernel Launcher

A new implementation for a [_kernel launcher_](../contributors/system-architecture.md#kernel-launchers) becomes
necessary when you want to introduce another kind of kernel to an existing configuration. Out of the box, Gateway
Provisioners provides [kernel launchers](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/kernel-launchers)
that support the IPython kernel ([and subclasses thereof](#invoking-subclasses-of-ipykernelkernelbasekernel)), the
Apache Toree scala kernel, and the R kernel - IRKernel. There are other "language-agnostic kernel launchers"
provided by Remote Provisioners, but those are used in container environments to start the container or pod where
the "kernel image" uses one of the three _language-based_ launchers to start the kernel within the container.

Its generally recommended that the launcher be written in the language of the kernel, but that is not a requirement
so long as the launcher can start and manage the kernel's lifecycle and issue interrupts (if the kernel does not
support message-based interrupts itself).

The four tasks of a kernel launcher are:

1. Create the necessary connection information based on the five zero-mq ports, a signature key and algorithm
   specifier, along with a _server listener_ socket.
1. Conveyance of the connection (and listener socket) information back to the host application (Gateway Provisioners)
   process after properly encrypting the information.
1. Invocation of the target kernel.
1. Listen for interrupt and shutdown requests from the host application on the communication socket and carry out
   the action when appropriate.

## Creating the Connection Information

If your target kernel exists, then there is probably support for creating ZeroMQ ports. If this proves difficult,
you may be able to take a _hybrid approach_ where the connection information, encryption and listener portion of
things is implemented in Python, while invocation takes place in the native language. This is how the
[R kernel-launcher](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/kernel-launchers/R/scripts)
support is implemented.

When creating the connection information, your kernel launcher should handle the possibility that the `--port-range`
option has been specified such that each port should reside within the specified range.

The port used between the host application and the kernel launcher, known as the _communication port_, should also
adhere to the port range. It is not required that this port be ZeroMQ (and is not a ZMQ port in existing
implementations).

Here's where the Python (and R) [ports are selected](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/kernel-launchers/shared/scripts/server_listener.py#L163-L180),
adhering to any port range restrictions.

## Encrypting the Connection Information

The next task of the kernel launcher is sending the connection information back to the host server. Prior to doing
this, the connection information, including the communication port, is encrypted using AES encryption and a
16-byte key. The AES key is then encrypted using the public key specified in the `public_key` parameter. These
two fields (the AES-encrypted payload and the public-key-encrypted AES key) are then included into a JSON
structure that also include the launcher's version information and base64-encoded. Here's such an example
from the [Python (and R) kernel launchers](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/kernel-launchers/shared/scripts/server_listener.py#L77-L100).

The payload is then [sent back on a socket](https://github.com/jupyter-server/gateway_provisioners/blob/9de8af8a361aa779f8eb4d10585c0d917bb3731f/gateway_provisioners/kernel-launchers/shared/scripts/server_listener.py#L102-L139)
identified by the `--response-address` option.

## Invoking the Target Kernel

For the R kernel launcher, the kernel is started using [`IRKernel::main()`](https://github.com/jupyter-server/gateway_provisioners/blob/9de8af8a361aa779f8eb4d10585c0d917bb3731f/gateway_provisioners/kernel-launchers/R/scripts/launch_IRkernel.R#L232)
after the `SparkContext` is initialized based on the `spark-context-initialization-mode` parameter.

The scala kernel launcher works similarly in that the Apache Toree kernel provides an
["entrypoint" to start the kernel](https://github.com/jupyter-server/gateway_provisioners/blob/9de8af8a361aa779f8eb4d10585c0d917bb3731f/gateway_provisioners/kernel-launchers/scala/toree-launcher/src/main/scala/launcher/ToreeLauncher.scala#L312),
however, because the Toree kernel initializes a `SparkContext` itself, the need to do so is conveyed directly to the kernel.

For the Python kernel launcher, it creates a namespace instance that contains the `SparkContext` information, if
requested to do so via the `spark-context-initialization-mode` parameter, instantiates an `IPKernelApp` instance
using the configured namespace, then calls the
[`start()`](https://github.com/ipython/ipykernel/blob/6f448d280dadbff7245f4b28b5e210c899d79342/ipykernel/kernelapp.py#L694) method.

### Invoking Subclasses of `ipykernel.kernelbase.Kernel`

Because the python kernel launcher uses `IPKernelApp`, support for any subclass of `ipykernel.kernelbase.Kernel`
can be launched by Gateway Provisioner's Python kernel launcher.

To specify an alternate subclass, add `--kernel-class-name` (along with the specified dotted class string) to
the `kernel.json` file's `argv` stanza. Gateway Provisioner's Python launcher will import that class and pass it as
a parameter to `IPKernelApp.initialize()`.

````{tip}
When generating kernel specfiications via the CLI tooling, this option is available via the
`--ipykernel-subclass-name` parameter.

For example, to generate the equivalent of the JSON below, enter:
```bash
jupyter ssh-spec install --ipykernel-subclass-name echo_kernel.kernel.EchoKernel --kernel-name echo --display-name Echo
```
````

Here's an example `kernel.json` file that launches the "echo" kernel using the `DistributedProvisioner`:

```JSON
{
  "argv": [
    "python",
    "/usr/local/share/jupyter/kernels/echo/scripts/launch_ipykernel.py",
    "--kernel-id",
    "{kernel_id}",
    "--port-range",
    "{port_range}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--kernel-class-name",
    "echo_kernel.kernel.EchoKernel"
  ],
  "env": {},
  "display_name": "Echo",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "debugger": true,
    "kernel_provisioner": {
      "provisioner_name": "distributed-provisioner",
      "config": {
        "launch_timeout": 30
      }
    }
  }
}
```

```{attention}
The referenced `kernel-class-name` package must be properly installed on all nodes/images where the associated
kernel will run.
```

## Listening for Interrupt and Shutdown Requests

The last task that must be performed by a kernel launcher is to listen on the communication port for work. There are
currently two requests sent on the port, a signal event and a shutdown request.

### Signal Event

The signal event is of the form `{"signum": n}` where the string `'signum'` indicates a signal event and `n` is
an integer specifying the signal number to send to the kernel. Typically, the value of `n` is `2` representing
`SIGINT` and used to interrupt any current processing. As more kernels adopt a message-based interrupt approach,
this will not be as common. Gateway Provisioners also use this event to perform its `poll()` implementation by
sending `{"signum": 0}`. Raising a signal of 0 to a process is a common way to determine the process is still alive.

### Shutdown Request

A shutdown request is sent when the Gateway Provisioners has typically terminated the kernel, and it's just performing
its final cleanup. The form of this request is `{"shutdown": 1}`. This is what instructs the launcher to abandon
listening on the communication socket and to exit.

Here's an example from the Python (and R) server listener code of
[handling host-initiated requests](https://github.com/jupyter-server/gateway_provisioners/blob/9de8af8a361aa779f8eb4d10585c0d917bb3731f/gateway_provisioners/kernel-launchers/shared/scripts/server_listener.py#L231-L245).

## Other Parameters

Besides `--port-range`, `--public-key`, and `--response-address`, the kernel launcher needs to support
`--kernel-id` that indicates the kernel's ID as known to the host server (mostly for log reconciliation). It
should also tolerate the existence of `--spark-context-initialization-mode` but, unless applicable for Spark
environments, should only support values of `"none"` for this option.
