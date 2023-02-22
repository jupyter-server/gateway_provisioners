# Implementing a Kernel Specification

If you find yourself [implementing a kernel launcher](kernel-launcher.md), you'll need a way to
make that kernel and kernel launcher available to applications. This is accomplished via the
_kernel specification_ or _kernelspec_.

Kernelspecs reside in well-known directories. For multi-tenant installations, where users may share kernel
specifications, we generally recommend they reside in `/usr/local/share/jupyter/kernels` where each entry in this
directory is a directory representing the name of the kernel. The kernel specification is represented by the
file `kernel.json`, the contents of which essentially indicate what environment variables should be present in
the kernel process (via the `env` _stanza_) and which command (and arguments) should be issued to start the kernel
process (via the `argv` _stanza_). The JSON also includes a `metadata` stanza that contains the kernel provisioner
configuration, along with which provisioner to instantiate to help manage the kernel process's lifecycle.

One approach the generated Gateway Provisioners kernel specifications take is to include a shell script that actually
issues the `spark-submit` request. It is this shell script (typically named `run.sh`) that is referenced in the
`argv` stanza.

Here's an example from a generated kernel specification for Spark running in a Hadoop YARN cluster:

```JSON
{
  "argv": [
    "/usr/local/share/jupyter/kernels/yarn_spark_python/bin/run.sh",
    "--kernel-id",
    "{kernel_id}",
    "--port-range",
    "{port_range}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--spark-context-initialization-mode",
    "lazy",
    "--kernel-class-name",
    "ipykernel.ipkernel.IPythonKernel"
  ],
  "env": {
    "SPARK_HOME": "/opt/spark",
    "PYSPARK_PYTHON": "/opt/miniconda3/envs/provisioners/bin/python",
    "PYTHONPATH": "${HOME}/.local/lib/python3.7/site-packages:/opt/spark/python",
    "SPARK_OPTS": "--master yarn --deploy-mode cluster --name ${KERNEL_ID:-ERROR__NO__KERNEL_ID} --conf spark.yarn.submit.waitAppCompletion=false --conf spark.yarn.appMasterEnv.PYTHONUSERBASE=/home/${KERNEL_USERNAME}/.local --conf spark.yarn.appMasterEnv.PYTHONPATH=${HOME}/.local/lib/python3.7/site-packages:/opt/spark/python --conf spark.yarn.appMasterEnv.PATH=/opt/miniconda3/envs/provisioners/bin:$PATH  ${KERNEL_EXTRA_SPARK_OPTS}",
    "LAUNCH_OPTS": ""
  },
  "display_name": "Spark Python (YARN Cluster)",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "kernel_provisioner": {
      "provisioner_name": "yarn-provisioner",
      "config": {
        "launch_timeout": 30
      }
    }
  }
}
```

where [`run.sh`](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/kernel-specs/yarn_spark_python/bin/run.sh)
issues `spark-submit` specifying the kernel launcher as the "application":

```bash
eval exec \
     "${SPARK_HOME}/bin/spark-submit" \
     "${SPARK_OPTS}" \
     "${IMPERSONATION_OPTS}" \
     "${PROG_HOME}/scripts/launch_ipykernel.py" \
     "${LAUNCH_OPTS}" \
     "$@"
```

For container-based environments, the `argv` may instead reference a script that is meant to create the container pod
(for Kubernetes). For these, we use a [template file](https://github.com/jupyter-server/gateway_provisioners/blob/main/gateway_provisioners/kernel-launchers/kubernetes/scripts/kernel-pod.yaml.j2)
that operators can adjust to meet the needs of their environment. Here's how that `kernel.json` looks:

```json
{
  "argv": [
    "python",
    "/usr/local/share/jupyter/kernels/k8s_python/scripts/launch_kubernetes.py",
    "--kernel-id",
    "{kernel_id}",
    "--port-range",
    "{port_range}",
    "--response-address",
    "{response_address}",
    "--public-key",
    "{public_key}",
    "--kernel-class-name",
    "ipykernel.ipkernel.IPythonKernel"
  ],
  "env": {},
  "display_name": "Kubernetes Python",
  "language": "python",
  "interrupt_mode": "signal",
  "metadata": {
    "debugger": true,
    "kernel_provisioner": {
      "provisioner_name": "kubernetes-provisioner",
      "config": {
        "image_name": "elyra/kernel-py:dev",
        "launch_timeout": 30
      }
    }
  }
}
```

When using the `launch_ipykernel` launcher (aka the Python kernel launcher), subclasses of `ipykernel.kernelbase.Kernel`
can be launched. By default, this launcher uses the classname `"ipykernel.ipkernel.IPythonKernel"`, but other
subclasses of `ipykernel.kernelbase.Kernel` can be specified by adding a `--kernel-class-name` parameter to the `argv`
stanza. See [Invoking subclasses of `ipykernel.kernelbase.Kernel`](kernel-launcher.md#invoking-subclasses-of-ipykernelkernelbasekernel)
for more information.

As should be evident, kernel specifications are highly tuned to the runtime environment so your needs may be different,
but _should_ resemble the approaches we've taken so far.
