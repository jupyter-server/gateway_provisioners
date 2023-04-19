# Kubernetes deployments

Because Gateway Provisioners is a _library package_ and not an _application_, deployment into Kubernetes
configurations consists of ensuring that the _host application image_ has the appropriate kernel specifications in place
and that necessary configuration items (typically environment variables in containerized deployments) are
present in the host application.

```{tip}
The following provides information for the kinds of tasks that should be considered when deploying applications
that use Gateway Provisioners on Kubernetes.  See our [_Application Support_ page](https://github.com/jupyter-server/gateway_provisioners/tree/main/gateway_provisioners/app-support/README.md)
for examples of how to configure and deploy such applications.
```

## Generating Kernel Specifications

Kernelspec generation for Kubernetes deployments is performed using the `jupyter-k8s-spec` command.  Because
the host application will also reside within a docker image, the commands are usually placed into a Dockerfile
that _extends_ an existing image.  However, some may choose to `docker exec` into a running container, perform and test
the necessary configuration, then use `docker commit` to generate a new image.  That said, the following will assume a
Dockerfile approach.

To generate a default kernel specification (where Python is the default kernel) enter:

```dockerfile
RUN jupyter k8s-spec install
```

which produces the following output...

```text
[I 2023-02-16 10:39:37.538 K8sSpecInstaller] Installing kernel specification for 'Kubernetes Python'
[I 2023-02-16 10:39:37.948 K8sSpecInstaller] Installed kernelspec k8s_python in /usr/local/share/jupyter/kernels/k8s_python
```

and the following set of files and directories:

```text
/usr/local/share/jupyter/kernels/k8s_python
kernel.json logo-64x64.png

/usr/local/share/jupyter/kernels/k8s_python/scripts:
launch_kubernetes.py
kernel-pod.yaml.j2
```

where each provides the following function:

- `kernel.json` - the primary file that the host application uses to discover a given kernel's availability.
  This file contains _stanzas_ that describe the kernel's argument vector (`argv`), its runtime environment (`env`),
  its display name (`display_name`) and language (`language`), as
  well as its kernel provisioner's configuration (`metadata.kernel_provisioner`) - which, in this case, will reflect the
  `KubernetesProvisioner`.
- `logo-64x64.png` - the icon resource corresponding to this kernel specification.  Icon resource files must be start
  with the `logo-` prefix to be included in the kernel specification.
- `scripts/launch_kubernetes.py` - the "launcher" for the kernel pod.  This script processes its sibling Jinja
  templates by applying appropriate substitutes and creating each of the Kubernetes resources as described in the template.
- `scripts/kernel-pod.yaml.j2` - the Jinja template describing the to-be-launched kernel pod corresponding to the
  kernel image identified by the `metadata.kernel_provisioner.config.image_name` entry.  This file can be modified to
  include instructions for volume mounts, etc., for establishing the pod's configuration.
- `bin/run.sh` - This file will be present only when `--spark` is specified.  The first entry in the `kernel.json`'s
  `argv` stanza will be a reference to `bin/run.sh`. This script sets up and invokes the `spark-submit` command that
  is responsible for interacting with the Spark-on-Kubernetes resource manager.  With the introduction of Spark Pod
  Templates, we can leverage the same templating behavior in Spark-based environments.  As a result, both the driver
  and executor pods will have similar configurations.

```{seealso}
See [Command-line Options](#command-line-options) below for how to adjust the `image-name`, `display-name`, and
others.
```

### Deploying Custom Resource Definitions

Gateway Provisioners currently supports one form of Custom Resource Definitions (CRDs) via the
[`SparkOperatorProvisioner`](../contributors/system-architecture.md#sparkoperatorprovisioner).  To generate a kernel
specification to use `SparkOperatorProvisioner`, in addition to including the `--spark` option, you will also include the
`--crd` option to `jupyter k8s-spec install`.

```dockerfile
RUN jupyter k8s-spec install --crd --spark
```

which produces the following output...

```text
[I 2023-04-19 10:18:09.963 K8sSpecInstaller] Installing kernel specification for 'Kubernetes Spark Operator'
[I 2023-04-19 10:18:10.360 K8sSpecInstaller] Installed kernelspec k8s_python_spark_operator in /usr/local/share/jupyter/kernels/k8s_python_spark_operator
```

and the following set of files and directories:

```text
/usr/local/share/jupyter/kernels/k8s_python_spark_operator
kernel.json logo-64x64.png

/usr/local/share/jupyter/kernels/k8s_python_spark_operator/scripts:
launch_custom_resource.py
sparkoperator.k8s.io-v1beta2.yaml.j2
```

There are a few things worth noting here.

1. The `scripts` directory contains a different set of scripts.  This is because the SparkOperator requires a
   slightly different launch script and its yaml definitions are different enough to warrant separation.
1. Although this provisioner uses Spark, there is no `run` sub-directory created that contains a `spark-submit`
   command.  Instead, the appropriate CRD is created which performs the application's submission to Spark directly.
1. The yaml template name is a composition of the provisioner's [`group` and `version` attributes](../contributors/system-architecture.md/#sparkoperatorprovisioner).
   In this case, the `group` is `sparkoperator.k8s.io` and `version` is `v1beta2`.

````{note}
If you plan to use kernel specifications leveraging `SparkOperatorProvisioner`, ensure that the
[Kubernetes Operator for Apache Spark is installed](https://github.com/GoogleCloudPlatform/spark-on-k8s-operator#installation)
in your Kubernetes cluster.

```{tip}
To ensure the proper flow of environment variables to your spark operator, make sure the
webhook server is enabled when deploying the helm chart:

`helm install my-release spark-operator/spark-operator --namespace spark-operator --set webhook.enable=true`
````

### Generating Multiple Specifications

Its common practice to support multiple languages or use different images for kernels of the same language.  For each
of those differences, a separate installation command should be provided:

```dockerfile
RUN jupyter k8s-spec install --image-name my-numpy-image:dev --kernel-name my_numpy_kernel_py --display-name "My Numpy"
RUN jupyter k8s-spec install --image-name my-tensor-image:dev --kernel-name my_tensor_kernel_py --display-name "My Tensorflow"
RUN jupyter k8s-spec install --image-name my-R-image:dev --language R --display-name "My R Kernel"
```

### Kubernetes Kernel Instances

Gateway Provisioners currently supports the launching of regular (_vanilla_) and spark-based kernels within a Kubernetes cluster.
When kernels are launched, Gateway Provisioners is responsible for creating the appropriate entities. The kind of
entity created is a function of whether the kernel is a regular or spark-based kernel specification.

Regular kernels are launched as a kernel pod based on the `scripts/kernel-pod.yaml.j2` template via the
`scripts/launch_kubernetes.py` script, both of which are located in the `scripts` directory.  Spark-based kernels are
launched via `spark-submit` in the `bin/run.sh` script triggering the creation of a _driver_ pod and one or more
_executor_ pods.

Items worth noting:

1. The launched pods' names will be composed of the launching username (`KERNEL_USERNAME`) and kernel-id. Some additional
   information is added to the spark-based pod names.
1. The pods will have 3 labels applied: `"kernel_id=<kernel-id>"`, `"component=kernel"`, and
   `"app=gateway-provisioners"` - similar to Docker.  The `component` label on the spark-based executor pods will hold a
   value of `worker` to distinguish them from the driver.
1. The pods will be launched within the same Kubernetes network as the host application.

## Namespaces

A best practice for Kubernetes applications running in an enterprise is to isolate applications via namespaces. There are
three ways namespaces can be used with respect to Gateway Provisioners: Shared Namespace, Bring-Your-Own Namespace,
and Automatic Namespace.

### Shared Namespace

Because Gateway Provisioners is a _library package_ and not its own application, the default namespace behavior is to
use a _shared namespace_.  That is, kernel pods launched by the application are placed into the same namespace as the
hosting application.  This option is controlled by two environment variables: `GP_SHARED_NAMESPACE` and `GP_NAMESPACE`.

#### `GP_SHARED_NAMESPACE`

This environment variable defaults to `True`.  When enabled, all kernel pods will be launched into the namespace
identified by `GP_NAMESPACE`.  No attempt is made to alter the configuration of `GP_NAMESPACE`.

#### `GP_NAMESPACE`

This environment variable identifies the namespace in which the host application is running.  It defaults to the
namespace named `default`, but its recommended that host application deployment configure its own namespace and this
environment variable be set to that value.

### Bring-Your-Own Namespace

Users can specify their own namespace be used by setting `GP_SHARED_NAMESPACE` = `False` and specifying the
`KERNEL_NAMESPACE` environment variable in the `env` stanza of the kernel's start request (e.g., `POST /api/kernels`).
This namespace model is preferred in multi-tenant configurations, particularly when a Gateway server is the host
application or, for example, in JupyterHub situations where Hub launches notebook servers into user-oriented namespaces.
(In this case, setting `GP_NAMESPACE` to the user-oriented namespace on each JupyterLab launch and using _Shared Namespace
modeling_, would have the same effect as setting `KERNEL_NAMESPACE` using the _Bring-Your-Own Namespace modeling_.)

When configured, Gateway Provisioners assumes the namespace identified by `KERNEL_NAMESPACE` already exists and is
properly configured from a resources and privileges standpoint.  In addition to providing `KERNEL_NAMESPACE`, users
must also provide the name of the service account privileged to create resources within the namespace.  The service
account name is conveyed via `KERNEL_SERVICE_ACCOUNT_NAME`.

Gateway Provisioners will not attempt to delete this namespace upon the kernel's termination.

### Automatic Namespace

Operators wanting the finest isolation level, where each kernel pod is launched into their own namespace, can do so by
disabling `GP_SHARED_NAMESPACE` and not setting `KERNEL_NAMESPACE`.  In these configurations, Gateway Provisioners will
_create_ a namespace corresponding to the values of `KERNEL_USERNAME`-`KERNEL_ID`, just as the pods are named.

This option requires higher-level privileges on the RBAC settings of the host application as the namespace must be
created on startup and deleted on termination.

#### Required RBAC Settings

As noted above, the ability to create and destroy namespaces at the time of kernel launch requires additional privileges
in the form of a `cluster-role`.  This role will require privileges to create and delete namespaces, services, and
role-bindings, among other things.  Because a new namespace will be created, a subsequent cluster-role should exist
that is for use by the kernel pod itself.  These two role definitions are provided below:

##### Application Cluster Role

This role is the responsibility of the host application deployment. The application name is specified here as
`gateway-provisioners` with a suggested name of `gateway-provisioners-controller`.

```yaml+jinja
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: gateway-provisioners-controller
  labels:
    app: gateway-provisioners
    component: gateway-provisioners
rules:
  - apiGroups: [""]
    resources: ["pods", "namespaces", "services", "configmaps", "secrets", "persistentvolumes", "persistentvolumeclaims"]
    verbs: ["get", "watch", "list", "create", "delete"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["rolebindings"]
    verbs: ["get", "list", "create", "delete"]
  - apiGroups: ["sparkoperator.k8s.io"]
    resources: ["sparkapplications", "sparkapplications/status", "scheduledsparkapplications", "scheduledsparkapplications/status"]
    verbs: ["get", "watch", "list", "create", "delete"]
```

```{note}
The reference to `apiGroups: ["sparkoperator.k8s.io"]` is forward-reaching as Gateway Provisioners doesn't currently
support Spark Operators - but plans to in the near future.
```

##### Kernel Cluster Role

The name of this role is conveyed from the host application to Gateway Provisioners via
the `GP_KERNEL_CLUSTER_ROLE` environment variable and defaults to `cluster-admin`, so operators are advised to create
a specific role for these purposes.  This role is responsible for managing resources within the newly-created namespace.\
While the role is a `cluster-role`, it is only _bound_ via a `role-binding` binding the cluster role to the namespace
and its service account referenced by `KERNEL_SERVICE_ACCOUNT_NAME`.

Here is the general yaml describing this configuration and suggests a name of `kernel-controller`:

```yaml+jinja
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  # Referenced by GP_KERNEL_CLUSTER_ROLE in the Deployment
  name: kernel-controller
  labels:
    app: gateway-provisioners
    component: kernel
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "watch", "list", "create", "delete"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["list", "create"]
  - apiGroups: [""]
    resources: ["services", "persistentvolumeclaims"]
    verbs: ["list"]
```

## Unconditional Volume Mounts

Unconditional volume mounts can be added in the `kernel-pod.yaml.j2` template. An example of these unconditional
volume mounts can be found when extending docker shared memory. For some I/O jobs the pod will need more than
the default `64mb` of shared memory on the `/dev/shm` path.

```yaml+jinja
volumeMounts:
# Define any "unconditional" mounts here, followed by "conditional" mounts that vary per client
{% if kernel_volume_mounts is defined %}
  {% for volume_mount in kernel_volume_mounts %}
- {{ volume_mount }}
  {% endfor %}
{% endif %}
volumes:
# Define any "unconditional" volumes here, followed by "conditional" volumes that vary per client
{% if kernel_volumes is defined %}
{% for volume in kernel_volumes %}
- {{ volume }}
{% endfor %}
{% endif %}
```

The conditional volumes are handled by the loops inside the yaml file. Any unconditional volumes can be added
before these conditions. In the scenario where the `/dev/shm` will need to be expanded the following mount
has to be added.

```yaml+jinja
volumeMounts:
# Define any "unconditional" mounts here, followed by "conditional" mounts that vary per client
- mountPath: /dev/shm
  name: dshm
{% if kernel_volume_mounts is defined %}
  {% for volume_mount in kernel_volume_mounts %}
- {{ volume_mount }}
  {% endfor %}
{% endif %}
volumes:
# Define any "unconditional" volumes here, followed by "conditional" volumes that vary per client
- name: dshm
emptyDir:
  medium: Memory
{% if kernel_volumes is defined %}
{% for volume in kernel_volumes %}
- {{ volume }}
{% endfor %}
{% endif %}
```

## Kubernetes Resource Quotas

When deploying kernels on a Kubernetes cluster a best practice is to define request and limit quotas for CPUs,
GPUs, and Memory. These quotas can be defined from the client via `KERNEL_`-prefixed environment variables which are
passed through to the kernel at startup.

- `KERNEL_CPUS` - CPU Request by Kernel
- `KERNEL_MEMORY` - MEMORY Request by Kernel
- `KERNEL_GPUS` - GPUS Request by Kernel
- `KERNEL_CPUS_LIMIT` - CPU Limit
- `KERNEL_MEMORY_LIMIT` - MEMORY Limit
- `KERNEL_GPUS_LIMIT` - GPUS Limit

Memory and CPU units are based on the
[Kubernetes Official Documentation](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
while GPU is using the NVIDIA `nvidia.com/gpu` parameter. The desired units should be included in the variable's value.

When defined, these variables are then substituted into the appropriate location of the corresponding
`kernel-pod.yaml.j2` template.

```yaml+jinja
{% if kernel_cpus is defined or kernel_memory is defined or kernel_gpus is defined or kernel_cpus_limit is defined or kernel_memory_limit is defined or kernel_gpus_limit is defined %}
  resources:
    {% if kernel_cpus is defined or kernel_memory is defined or kernel_gpus is defined %}
    requests:
      {% if kernel_cpus is defined %}
      cpu: "{{ kernel_cpus }}"
      {% endif %}
      {% if kernel_memory is defined %}
      memory: "{{ kernel_memory }}"
      {% endif %}
      {% if kernel_gpus is defined %}
      nvidia.com/gpu: "{{ kernel_gpus }}"
      {% endif %}
    {% endif %}
    {% if kernel_cpus_limit is defined or kernel_memory_limit is defined or kernel_gpus_limit is defined %}
    limits:
      {% if kernel_cpus_limit is defined %}
      cpu: "{{ kernel_cpus_limit }}"
      {% endif %}
      {% if kernel_memory_limit is defined %}
      memory: "{{ kernel_memory_limit }}"
      {% endif %}
      {% if kernel_gpus_limit is defined %}
      nvidia.com/gpu: "{{ kernel_gpus_limit }}"
      {% endif %}
    {% endif %}
  {% endif %}
```

## Other Configuration Items

There are some environment variables that can be set in the host application's environment that affect how Gateway
Provisioners operate within a Kubernetes environment.  For example, `GP_MIRROR_WORKING_DIRS` can be set
to `True`, instructing Gateway Provisioners to set the launched container's working directory to the value of
`KERNEL_WORKING_DIR`.  When this environment variable is enabled, it usually implies that volume mounts are in play
such that the per-user volumes are then available to the launched container.

Other [environment variables](config-add-env.md#additional-environment-variables) applicable to Kubernetes
configurations are `GP_NAMESPACE` and `GP_PROHIBITED_UIDS`.

````{seealso}
```{eval-rst}
See :ref:`configuring-gp`, with a focus on Kubernetes-specific options, for
additional configuration options within the host application.
```
````

## Command-line Options

The following is produced using `jupyter k8s-spec install --help` and displays the complete set of command-line
options:

```text
Creates a Jupyter kernel specification for use within a Kubernetes cluster.

Options
=======
The options below are convenience aliases to configurable class-options,
as listed in the "Equivalent to" description-line of the aliases.
To see all configurable class-options for some <cmd>, use:
    <cmd> --help-all

--spark
    Install kernelspec for use with Spark.  When combined with --crd,
    will configure the SparkOperatorProvisioner for Spark Application CRDs.
    Equivalent to: [--K8sSpecInstaller.spark=True]
--user
    Try to install the kernel spec to the per-user directory instead of the system or environment directory.
    Equivalent to: [--BaseSpecApp.user=True]
--replace
    If a kernel specification already exists in the destination, allow for its replacement.
    Equivalent to: [--BaseSpecApp.replace=True]
--sys-prefix
    Specify a prefix to install to, e.g. an env. The kernelspec will be installed in PREFIX/share/jupyter/kernels/
    Equivalent to: [--BaseSpecApp.prefix=/opt/miniconda3/envs/provisioners]
--debug
    set log level to logging.DEBUG (maximize logging output)
    Equivalent to: [--Application.log_level=10]
--tensorflow
    Install kernelspec for use with Tensorflow.
    Equivalent to: [--K8sSpecInstaller.tensorflow=True]
--crd
    Install kernelspec for use with a Custom Resource Definition.  When combined with --spark,
    will configure the SparkOperatorProvisioner for Spark Application CRDs.
    Equivalent to: [--K8sSpecInstaller.crd=True]
--image-name=<Unicode>
    The kernel image to use for this kernel specification. If this specification
    is enabled for Spark usage, this image will be the driver image.
    (GP_IMAGE_NAME env var)
    Default: None
    Equivalent to: [--K8sSpecInstaller.image_name]
--executor-image-name=<Unicode>
    The executor image to use for this kernel specification.  Only applies to
    Spark-enabled kernel specifications.  (GP_EXECUTOR_IMAGE_NAME env var)
    Default: None
    Equivalent to: [--K8sSpecInstaller.executor_image_name]
--spark-home=<Unicode>
    Specify where the spark files can be found.
    Default: '/opt/spark'
    Equivalent to: [--BaseSpecSparkApp.spark_home]
--spark-init-mode=<Unicode>
    Spark context initialization mode.  Must be one of ['lazy', 'eager', 'none'].
        Default = lazy.
    Default: 'lazy'
    Equivalent to: [--BaseSpecSparkApp.spark_init_mode]
--extra-spark-opts=<Unicode>
    Specify additional Spark options.
    Default: ''
    Equivalent to: [--BaseSpecSparkApp.extra_spark_opts]
--prefix=<Unicode>
    Specify a prefix to install to, e.g. an env. The kernelspec will be
    installed in PREFIX/share/jupyter/kernels/
    Default: ''
    Equivalent to: [--BaseSpecApp.prefix]
--kernel-name=<Unicode>
    Install the kernel spec into a directory with this name.
    Default: ''
    Equivalent to: [--BaseSpecApp.kernel_name]
--display-name=<Unicode>
    The display name of the kernel - used by user-facing applications.
    Default: ''
    Equivalent to: [--BaseSpecApp.display_name]
--language=<Unicode>
    The language of the kernel referenced in the kernel specification.  Must be one of
        'Python', 'R', or 'Scala'.  Default = 'Python'.
    Default: 'Python'
    Equivalent to: [--BaseSpecApp.language]
--authorized-users=<set-item-1>...
    List of user names against which KERNEL_USERNAME will be compared. Any match
    (case-sensitive) will allow the kernel's launch, otherwise an HTTP 403
    (Forbidden) error will be raised.  The set of unauthorized users takes
    precedence. This option should be used carefully as it can dramatically
    limit who can launch kernels. To specify multiple names via the CLI,
    separate options must be provided for each entry. (GP_AUTHORIZED_USERS env
    var - non-bracketed, just comma-separated)
    Default: set()
    Equivalent to: [--BaseSpecApp.authorized_users]
--unauthorized-users=<set-item-1>...
    List of user names against which KERNEL_USERNAME will be compared. Any match
    (case-sensitive) will prevent the kernel's launch and result in an HTTP 403
    (Forbidden) error. To specify multiple names via the CLI, separate options
    must be provided for each entry. (GP_UNAUTHORIZED_USERS env var - non-
    bracketed, just comma-separated)
    Default: {'root'}
    Equivalent to: [--BaseSpecApp.unauthorized_users]
--port-range=<Unicode>
    Specifies the lower and upper port numbers from which ports are created. The
    bounded values are separated by '..' (e.g., 33245..34245 specifies a range
    of 1000 ports to be randomly selected). A range of zero (e.g., 33245..33245
    or 0..0) disables port-range enforcement.  (GP_PORT_RANGE env var)
    Default: '0..0'
    Equivalent to: [--BaseSpecApp.port_range]
--launch-timeout=<Int>
    Number of ports to try if the specified port is not available
    (GP_LAUNCH_TIMEOUT env var)
    Default: 30
    Equivalent to: [--BaseSpecApp.launch_timeout]
--ipykernel-subclass-name=<Unicode>
    For Python kernels, the name of the ipykernel subclass.
    Default: 'ipykernel.ipkernel.IPythonKernel'
    Equivalent to: [--BaseSpecApp.ipykernel_subclass_name]
--log-level=<Enum>
    Set the log level by value or name.
    Choices: any of [0, 10, 20, 30, 40, 50, 'DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL']
    Default: 30
    Equivalent to: [--Application.log_level]
--config=<Unicode>
    Full path of a config file.
    Default: ''
    Equivalent to: [--JupyterApp.config_file]

Examples
--------

    jupyter-k8s-spec install --language=R --kernel-name=r_k8s --image-name=foo/my_r_kernel_image:v4_0

    jupyter-k8s-spec install --language=Scala --spark --kernel-name=scala_k8s_spark --display-name='Scala on Kubernetes with Spark'

    jupyter-k8s-spec install --spark --crd --display-name='Python SparkOperator"

To see all available configurables, use `--help-all`.
```
