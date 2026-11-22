# Environment variables that assist in troubleshooting

The following environment variables may be useful for troubleshooting:

```text
  GP_DOCKER_LOG_LEVEL=WARNING
    By default, the docker client library is too verbose for its logging.  This
    value can be adjusted in situations where docker troubleshooting may be warranted.

  GP_KUBERNETES_LOG_LEVEL=WARNING
    By default, the Kubernetes client library is too verbose for its logging.  This
    value can be adjusted in situations where kubernetes troubleshooting may be
    warranted.

  GP_LOG_LEVEL=10
    Used by remote launchers and server listeners (where the kernel runs), this
    indicates the level of logging used by those entities.  Level 10 (DEBUG) is
    recommended since they don't do verbose logging.

  GP_MAX_POLL_ATTEMPTS=10
    Polling is used in various places during life-cycle management operations - like
    determining if a kernel process is still alive, stopping the process, waiting
    for the process to terminate, etc.  As a result, it may be useful to adjust
    this value during those kinds of troubleshooting scenarios, although that
    should rarely be necessary.

  GP_POLL_INTERVAL=0.5
    The interval (in seconds) to wait before checking poll results again.

  GP_REMOVE_CONTAINER=True
    Used by launch_docker.py, indicates whether the kernel's docker container should be
    removed following its shutdown.  Set this value to 'False' if you want the container
    to be left around in order to troubleshoot issues.  Remember to set back to 'True'
    to restore normal operation.

  GP_SOCKET_TIMEOUT=5.0
    The time (in seconds) the host server will wait on its connection file socket
    waiting on return from a remote kernel launcher.  Upon timeout, the operation
    will be retried immediately, until the overall time limit has been exceeded.

  GP_SSH_LOG_LEVEL=WARNING
    By default, the paramiko ssh library is too verbose for its logging.  This
    value can be adjusted in situations where ssh troubleshooting may be warranted.

  GP_YARN_LOG_LEVEL=WARNING
    By default, the yarn-api-client library is too verbose for its logging.  This
    value can be adjusted in situations where YARN troubleshooting may be warranted.
```

## Kernel environment in logs

At `DEBUG` level, the provisioners log the environment each kernel is launched with.
Every variable name is logged, sorted, but values are logged only for a fixed set of
non-secret identifiers that Gateway Provisioners sets or uses - for example `KERNEL_ID`,
`KERNEL_USERNAME`, `KERNEL_NAMESPACE` and `KERNEL_IMAGE` (see `env_log_allowlist` in
`gateway_provisioners/remote_provisioner.py` for the complete list). All other values are
shown as `***` since kernel environments commonly carry credentials:

```text
RemoteProvisionerBase.launch_kernel() env: {'AWS_SECRET_ACCESS_KEY': '***', 'KERNEL_ID': '0f2b...', 'KERNEL_USERNAME': 'alice', 'PATH': '***', ...}
```

Similarly, the `bootstrap-kernel.sh` script used by kernel images prints only the names of
its environment variables.
