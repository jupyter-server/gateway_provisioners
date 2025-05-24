#!/opt/conda/bin/python
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import argparse
import os
import sys
from typing import List

import urllib3
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from kubernetes import client, config  # type:ignore[import-untyped]
from kubernetes.client.rest import ApiException  # type:ignore[import-untyped]

urllib3.disable_warnings()

KERNEL_POD_TEMPLATE_PATH = "/kernel-pod.yaml.j2"


def generate_kernel_pod_yaml(keywords):
    """Return the kubernetes pod spec as a yaml string.

    - load jinja2 template from this file directory.
    - substitute template variables with keywords items.
    """
    j_env = Environment(
        loader=FileSystemLoader(os.path.dirname(__file__)),
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=select_autoescape(
            disabled_extensions=(
                "j2",
                "yaml",
            ),
            default_for_string=True,
            default=True,
        ),
    )
    # jinja2 template substitutes template variables with None though keywords doesn't
    # contain corresponding item. Therefore, no need to check if any are left unsubstituted.
    # Kubernetes API server will validate the pod spec instead.
    k8s_yaml = j_env.get_template(KERNEL_POD_TEMPLATE_PATH).render(**keywords)

    return k8s_yaml


def extend_pod_env(pod_def: dict) -> dict:
    """Extends the pod_def.spec.containers[0].env stanza with current environment."""
    env_stanza = pod_def["spec"]["containers"][0].get("env") or []

    # Walk current set of template env entries and replace those found in the current
    # env with their values (and record those items).   Then add all others from the env
    # that were not already.
    processed_entries: List[str] = []
    for item in env_stanza:
        item_name = item.get("name")
        if item_name in os.environ:
            item["value"] = os.environ[item_name]
            processed_entries.append(item_name)

    for name, value in os.environ.items():
        if name not in processed_entries:
            env_stanza.append({"name": name, "value": value})

    pod_def["spec"]["containers"][0]["env"] = env_stanza
    return pod_def


# A popular reason that lasts many APIs but is not a constant in the client lib
K8S_ALREADY_EXIST_REASON = "AlreadyExists"


def _parse_k8s_exception(exc: ApiException) -> str:
    """Parse the exception and return the error message from kubernetes api
    Args:
        exc (Exception): Exception object
    Returns:
        str: Error message from kubernetes api
    """
    # more exception can be parsed, but at the time of implementation we only need this one
    if exc.status == 409:
        if exc.reason == "Conflict" and f'"reason":{K8S_ALREADY_EXIST_REASON}' in exc.body:
            return K8S_ALREADY_EXIST_REASON
    return ""


def launch_kubernetes_kernel(
    kernel_id,
    port_range,
    response_addr,
    public_key,
    spark_context_init_mode,
    pod_template_file,
    spark_opts_out,
    kernel_class_name,
):
    # Launches a containerized kernel as a kubernetes pod.

    if os.getenv("KUBERNETES_SERVICE_HOST"):
        config.load_incluster_config()
    else:
        config.load_kube_config()

    # Capture keywords and their values.
    keywords = {}

    # Factory values...
    # Since jupyter lower cases the kernel directory as the kernel-name, we need to capture its case-sensitive
    # value since this is used to locate the kernel launch script within the image.
    # Ensure these key/value pairs are reflected in the environment.  We'll add these to the container's env
    # stanza after the pod template is generated.
    if port_range:
        os.environ["PORT_RANGE"] = port_range
    if public_key:
        os.environ["PUBLIC_KEY"] = public_key
    if response_addr:
        os.environ["RESPONSE_ADDRESS"] = response_addr
    if kernel_id:
        os.environ["KERNEL_ID"] = kernel_id
    if spark_context_init_mode:
        os.environ["KERNEL_SPARK_CONTEXT_INIT_MODE"] = spark_context_init_mode
    if kernel_class_name:
        os.environ["KERNEL_CLASS_NAME"] = kernel_class_name

    os.environ["KERNEL_NAME"] = os.path.basename(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )

    # Walk env variables looking for names prefixed with KERNEL_.  When found, set corresponding keyword value
    # with name in lower case.
    for name, value in os.environ.items():
        if name.startswith("KERNEL_"):
            keywords[name.lower()] = yaml.safe_load(value)

    # Substitute all template variable (wrapped with {{ }}) and generate `yaml` string.
    k8s_yaml = generate_kernel_pod_yaml(keywords)

    # For each k8s object (kind), call the appropriate API method.  Too bad there isn't a method
    # that can take a set of objects.
    #
    # Creation for additional kinds of k8s objects can be added below.  Refer to
    # https://github.com/kubernetes-client/python for API signatures.  Other examples can be found in
    # https://github.com/jupyter-server/enterprise_gateway/tree/main/enterprise_gateway/services/processproxies/k8s.py
    #
    pod_template = None
    kernel_namespace = keywords["kernel_namespace"]
    k8s_objs = yaml.safe_load_all(k8s_yaml)
    for k8s_obj in k8s_objs:
        if k8s_obj.get("kind"):
            if k8s_obj["kind"] == "Pod":
                #  print("{}".format(k8s_obj))  # useful for debug
                pod_template = extend_pod_env(k8s_obj)
                if pod_template_file is None:
                    try:
                        client.CoreV1Api(client.ApiClient()).create_namespaced_pod(
                            body=k8s_obj, namespace=kernel_namespace
                        )
                    except ApiException as exc:
                        if _parse_k8s_exception(exc) == K8S_ALREADY_EXIST_REASON:
                            (
                                client.CoreV1Api(client.ApiClient())
                                .list_namespaced_pod(
                                    namespace=kernel_namespace,
                                    label_selector=f"kernel_id={kernel_id}",
                                    watch=False,
                                )
                                .items[0]
                            )
                        else:
                            raise exc
            elif k8s_obj["kind"] == "Secret":
                if pod_template_file is None:
                    client.CoreV1Api(client.ApiClient()).create_namespaced_secret(
                        body=k8s_obj, namespace=kernel_namespace
                    )
            elif k8s_obj["kind"] == "PersistentVolumeClaim":
                if pod_template_file is None:
                    try:
                        client.CoreV1Api(
                            client.ApiClient()
                        ).create_namespaced_persistent_volume_claim(
                            body=k8s_obj, namespace=kernel_namespace
                        )
                    except ApiException as exc:
                        if _parse_k8s_exception(exc) == K8S_ALREADY_EXIST_REASON:
                            pass
                        else:
                            raise exc
            elif k8s_obj["kind"] == "PersistentVolume":
                if pod_template_file is None:
                    client.CoreV1Api(client.ApiClient()).create_persistent_volume(body=k8s_obj)
            else:
                sys.exit(
                    f"ERROR - Unhandled Kubernetes object kind '{k8s_obj['kind']}' found in yaml file - "
                    f"kernel launch terminating!"
                )
        else:
            print("ERROR processing Kubernetes yaml file - kernel launch terminating!")
            print(k8s_yaml)
            sys.exit(
                f"ERROR - Unknown Kubernetes object '{k8s_obj}' found in yaml file - kernel launch terminating!"
            )

    if pod_template_file:
        # TODO - construct other --conf options for things like mounts, resources, etc.
        # write yaml to file...
        stream = open(pod_template_file, "w")
        yaml.dump(pod_template, stream)

        # Build up additional spark options.  Note the trailing space to accommodate concatenation
        additional_spark_opts = (
            f"--conf spark.kubernetes.driver.podTemplateFile={pod_template_file} "
            f"--conf spark.kubernetes.executor.podTemplateFile={pod_template_file} "
        )
        assert pod_template is not None
        additional_spark_opts += _get_spark_resources(pod_template)

        if spark_opts_out:
            with open(spark_opts_out, "w+") as soo_fd:
                soo_fd.write(additional_spark_opts)
        else:  # If no spark_opts_out was specified, print to stdout in case this is an old caller
            print(additional_spark_opts)


def _get_spark_resources(pod_template: dict) -> str:
    # Gather up resources for cpu/memory requests/limits.  Since gpus require a "discovery script"
    # we'll leave that alone for now:
    # https://spark.apache.org/docs/latest/running-on-kubernetes.html#resource-allocation-and-configuration-overview
    #
    # The config value names below are pulled from:
    # https://spark.apache.org/docs/latest/running-on-kubernetes.html#container-spec
    spark_resources = ""
    containers = pod_template.get("spec", {}).get("containers", [])
    if containers:
        # We're just dealing with single-container pods at this time.
        resources = containers[0].get("resources", {})
        if resources:
            requests = resources.get("requests", {})
            if requests:
                cpu_request = requests.get("cpu")
                if cpu_request:
                    spark_resources += (
                        f"--conf spark.driver.cores={cpu_request} "
                        f"--conf spark.executor.cores={cpu_request} "
                    )
                memory_request = requests.get("memory")
                if memory_request:
                    spark_resources += (
                        f"--conf spark.driver.memory={memory_request} "
                        f"--conf spark.executor.memory={memory_request} "
                    )

            limits = resources.get("limits", {})
            if limits:
                cpu_limit = limits.get("cpu")
                if cpu_limit:
                    spark_resources += (
                        f"--conf spark.kubernetes.driver.limit.cores={cpu_limit} "
                        f"--conf spark.kubernetes.executor.limit.cores={cpu_limit} "
                    )
                memory_limit = limits.get("memory")
                if memory_limit:
                    spark_resources += (
                        f"--conf spark.driver.memory={memory_limit} "
                        f"--conf spark.executor.memory={memory_limit} "
                    )
    return spark_resources


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--kernel-id",
        dest="kernel_id",
        nargs="?",
        help="Indicates the id associated with the launched kernel.",
    )
    parser.add_argument(
        "--port-range",
        dest="port_range",
        nargs="?",
        metavar="<lowerPort>..<upperPort>",
        help="Port range to impose for kernel ports",
    )
    parser.add_argument(
        "--response-address",
        dest="response_address",
        nargs="?",
        metavar="<ip>:<port>",
        help="Connection address (<ip>:<port>) for returning connection file",
    )
    parser.add_argument(
        "--public-key",
        dest="public_key",
        nargs="?",
        help="Public key used to encrypt connection information",
    )
    parser.add_argument(
        "--spark-context-initialization-mode",
        dest="spark_context_init_mode",
        nargs="?",
        help="Indicates whether or how a spark context should be created",
        default="none",
    )
    parser.add_argument(
        "--pod-template",
        dest="pod_template_file",
        nargs="?",
        metavar="template filename",
        help="When present, yaml is written to file, no launch performed.",
    )
    parser.add_argument(
        "--spark-opts-out",
        dest="spark_opts_out",
        nargs="?",
        metavar="additional spark options filename",
        help="When present, additional spark options are written to file, "
        "no launch performed, requires --pod-template.",
    )
    parser.add_argument(
        "--kernel-class-name",
        dest="kernel_class_name",
        nargs="?",
        help="Indicates the name of the kernel class to use.  Must be a subclass of 'ipykernel.kernelbase.Kernel'.",
    )

    arguments = vars(parser.parse_args())
    kernel_id = arguments["kernel_id"]
    port_range = arguments["port_range"]
    response_addr = arguments["response_address"]
    public_key = arguments["public_key"]
    spark_context_init_mode = arguments["spark_context_init_mode"]
    pod_template_file = arguments["pod_template_file"]
    spark_opts_out = arguments["spark_opts_out"]
    kernel_class_name = arguments["kernel_class_name"]

    launch_kubernetes_kernel(
        kernel_id,
        port_range,
        response_addr,
        public_key,
        spark_context_init_mode,
        pod_template_file,
        spark_opts_out,
        kernel_class_name,
    )
