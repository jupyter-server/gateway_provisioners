# Connecting to a remote Gateway server

To leverage the benefits of most provisioners provided by Gateway Provisioners, it's helpful to redirect a
Jupyter server's kernel management to a Gateway server. This allows better separation of the user's
notebooks from the managed compute cluster (Kubernetes, Hadoop YARN, Docker Swarm, etc.) on which
the Gateway server resides. A Jupyter server can be configured to relay kernel requests to a Gateway server
in several ways.

```{note}
The following assumes a Gateway server has been configured and deployed.  Please consult the
[Operators Guide](/operators/index.rst) to deploy and configure Gateway Provisioners
within a Gateway server.
```

```{attention}
Enterprise Gateway will not be compatible with Gateway Provisioners until its 4.0 release.  As a result
the following assumes the targeted Gateway server is a Jupyter Kernel Gateway deployment.  While attempts
to connect to a deployment of Enterprise Gateway 3.x, the kernels provided by _that_ deployment will be
based on EG's process-proxies and not kernel provisioners.  Nevertheless, _these instructions_ are the
same since the GatewayClient support in Jupyter Server is backward compatible.
```

## Connecting via JupyterLab

Connecting to a Gateway server from JupyterLab (or Notebook) is fairly straightforward due to a rich set of
configuration capabilities and the fact that this capability has been supported for some time.

### Command line

To instruct the server to connect to a Gateway instance running on host `<GATEWAY_HOST_IP>` on port `<GATEWAY_PORT>`, the following command line options can be used:

```bash
jupyter lab --gateway-url=http://<GATEWAY_HOST_IP>:<GATEWAY_PORT> --GatewayClient.http_user=guest --GatewayClient.http_pwd=guest-password
```

### Configuration file

If command line options are not appropriate for your environment, the Jupyter server configuration file
can be used to express Gateway server options. Note however, that command line options always override
configuration file options.

In your `jupyter_server_config.py` file add the following for the equivalent options:

```python
c.GatewayClient.url = "http://<GATEWAY_HOST_IP>:<GATEWAY_PORT>"
c.GatewayClient.http_user = "guest"
c.GatewayClient.http_pwd = "guest-password"
```

### Docker image

All GatewayClient options have corresponding environment variable support, so if your Jupyter Lab or
Notebook installation is already in a docker image, a corresponding docker invocation would look something
like this:

```bash
docker run -t --rm \
  -e JUPYTER_GATEWAY_URL='http://<GATEWAY_HOST_IP>:<GATEWAY_PORT>' \
  -e JUPYTER_GATEWAY_HTTP_USER=guest \
  -e JUPYTER_GATEWAY_HTTP_PWD=guest-password \
  -e LOG_LEVEL=DEBUG \
  -p 8888:8888 \
  -v ${HOME}/notebooks/:/tmp/notebooks \
  -w /tmp/notebooks \
  my-image
```

Notebook files residing in `${HOME}/notebooks` can then be accessed via `http://localhost:8888`.

## Connecting via Papermill

Connecting to a Gateway server from Papermill is not nearly as common because Papermill is typically used local to
where the kernel will run.

### Creating a Papermill Engine

Connecting Papermill to a Gateway actually leverages the same `KernelManager` that is used when JupyterLab connects to
a Gateway server.  However, to set the class of a `KernelManager` to `jupyter_server.gateway.managers.GatewayKernelManager`
one must implement, and register (via entrypoints), a ["Papermill engine"](https://papermill.readthedocs.io/en/latest/extending-entry-points.html#developing-a-new-engine).

Once the engine is implemented and set to use the `GatewayKernelManager` class, Papermill can be invoked using:

```bash
papermill --engine MyPapermillEngine NotebookToExecute.ipynb OutputNotebook.ipynb
```

An example of a Papermill engine that supports connecting to a remote Gateway server can be found in the
[Elyra project](https://github.com/elyra-ai/elyra/blob/38d2c842a33358a1f3cc042a34d380026893e250/elyra/pipeline/elyra_engine.py#L25).

## Connection Timeouts

Sometimes, depending on the kind of cluster the Gateway server is servicing, connection establishment and
kernel startup can take a while (sometimes upwards of minutes). This is particularly true for managed
clusters that perform scheduling like Hadoop YARN or Kubernetes. In these configurations it is important
to configure both the connection and request timeout values.

The options `GatewayClient.connect_timeout` (env: `JUPYTER_GATEWAY_CONNECT_TIMEOUT`)
and `GatewayClient.request_timeout` (env: `JUPYTER_GATEWAY_REQUEST_TIMEOUT`) default to 40 seconds, but
can be configured as necessary.

The `KERNEL_LAUNCH_TIMEOUT` environment variable will be set from these values or vice versa (whichever is
greater). This value is used by Gateway Provisioners to determine when it should give up on waiting for
the kernel's startup to complete, while the other timeouts are used by Lab or Notebook when establishing
the connection to the Gateway server.
