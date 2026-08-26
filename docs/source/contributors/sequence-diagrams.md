# Sequence Diagrams

The following consists of various sequence diagrams you might find helpful. We plan to add
diagrams based on demand and contributions.

## Kernel Launch: Web Application to Kernel

This diagram depicts the interactions between components when a kernel start request
is submitted from a Web application running against a host application in which Gateway
Provisioners has been configured.

```{mermaid}
:align: center
:caption: Kernel Launch: Web Application to Kernel

sequenceDiagram
  participant WebApplication as Web Application
  participant HostApplication as Host Application
  participant KernelManager as Kernel Manager
  participant Provisioner
  participant Kernel
  participant ResourceManager as Resource Manager

  Note over WebApplication,ResourceManager: Kernel Launch

  WebApplication ->> HostApplication: https POST api/kernels
  HostApplication ->> KernelManager: start_kernel()
  KernelManager ->> Provisioner: launch_process()

  Provisioner ->> Kernel: launch kernel
  Provisioner ->> ResourceManager: confirm startup
  Kernel -->> Provisioner: connection info
  ResourceManager -->> Provisioner: state and host info
  Provisioner -->> KernelManager: complete connection info
  KernelManager ->> Kernel: TCP socket requests
  Kernel -->> KernelManager: TCP socket handshakes
  KernelManager -->> HostApplication: kernel-id
  HostApplication -->> WebApplication: api/kernels response

  Note over WebApplication,ResourceManager: Websocket Negotiation

  WebApplication ->> HostApplication: ws GET api/kernels
  HostApplication ->> Kernel: kernel_info_request message
  Kernel -->> HostApplication: kernel_info_reply message
  HostApplication -->> WebApplication: websocket upgrade response
```
