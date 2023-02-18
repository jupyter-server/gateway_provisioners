# Sequence Diagrams

The following consists of various sequence diagrams you might find helpful. We plan to add
diagrams based on demand and contributions.

## Kernel Launch: Web Application to Kernel

This diagram depicts the interactions between components when a kernel start request
is submitted from a Web application running against a host application in which Gateway
Provisioners has been configured.

```{seqdiag}
   :align: "center"
   :caption: "Kernel Launch: Web Application to Kernel"

seqdiag {
   edge_length = 180;
   span_height = 15;
   WebApplication  [label = "Web Application"];
   HostApplication  [label = "Host Application"];
   KernelManager  [label = "Kernel Manager"];
   Provisioner;
   Kernel;
   ResourceManager  [label = "Resource Manager"];

  === Kernel Launch ===

  WebApplication -> HostApplication [label = "https POST api/kernels "];
  HostApplication -> KernelManager [label = "start_kernel() "];
  KernelManager -> Provisioner [label = "launch_process() "];

  Provisioner -> Kernel [label = "launch kernel"];
  Provisioner -> ResourceManager [label = "confirm startup"];
  Kernel --> Provisioner [label = "connection info"];
  ResourceManager --> Provisioner [label = "state & host info"];
  Provisioner --> KernelManager [label = "complete connection info"];
  KernelManager -> Kernel [label = "TCP socket requests"];
  Kernel --> KernelManager [label = "TCP socket handshakes"];
  KernelManager --> HostApplication [label = "kernel-id"];
  HostApplication --> WebApplication [label = "api/kernels response"];

  === Websocket Negotiation ===

  WebApplication -> HostApplication [label = "ws GET api/kernels"];
  HostApplication -> Kernel [label = "kernel_info_request message"];
  Kernel --> HostApplication [label = "kernel_info_reply message"];
  HostApplication --> WebApplication [label = "websocket upgrade response"];
}
```
