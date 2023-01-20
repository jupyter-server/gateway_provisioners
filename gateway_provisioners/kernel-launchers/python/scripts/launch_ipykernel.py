# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import argparse
import logging
import os
import signal
import tempfile
from collections.abc import Callable
from threading import Thread
from typing import Any, Optional

from server_listener import setup_server_listener

LAUNCHER_VERSION = 1  # Indicate to server the version of this launcher (payloads may vary)

# Minimum port range size and max retries
min_port_range_size = int(os.getenv("MIN_PORT_RANGE_SIZE", "1000"))

log_level = os.getenv("LOG_LEVEL", "10")
log_level = int(log_level) if log_level.isdigit() else log_level

logging.basicConfig(format="[%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s] %(message)s")

# Protect the instance with a dunder so it isn't remove from the namespace
__logger = logging.getLogger("launch_ipykernel")
__logger.setLevel(log_level)

DEFAULT_KERNEL_CLASS_NAME = "ipykernel.ipkernel.IPythonKernel"
__spark_context = None


class ExceptionThread(Thread):
    # Wrap thread to handle the exception
    def __init__(self, target: Callable):
        self.target = target
        self.exc = None
        Thread.__init__(self)

    def run(self):
        try:
            self.target()
        except Exception as exc:
            self.exc = exc


def initialize_namespace(namespace: dict, cluster_type: str = "spark") -> None:
    """Initialize the kernel namespace.

    Parameters
    ----------
    namespace : Dict
        The namespace to initialize
    cluster_type : {'spark', 'dask', 'none'}
        The cluster type to initialize. ``'none'`` results in no variables in
        the initial namespace.
    """
    if cluster_type == "spark":
        try:
            from pyspark.sql import SparkSession
        except ImportError:
            __logger.info(
                "A spark context was desired but the pyspark distribution is not present.  "
                "Spark context creation will not occur."
            )
            return

        def initialize_spark_session():
            import atexit

            """Initialize Spark session and replace global variable
            placeholders with real Spark session object references."""
            spark = SparkSession.builder.getOrCreate()

            global __spark_context
            __spark_context = spark.sparkContext

            # Stop the spark session on exit
            atexit.register(lambda: spark.stop())

            namespace.update(
                {
                    "spark": spark,
                    "sc": spark.sparkContext,
                    "sql": spark.sql,
                }
            )

        init_thread = ExceptionThread(target=initialize_spark_session)
        spark = WaitingForSparkSessionToBeInitialized("spark", init_thread, namespace)
        sc = WaitingForSparkSessionToBeInitialized("sc", init_thread, namespace)

        def sql(query):
            """Placeholder function. When called will wait for Spark session to be
            initialized and call ``spark.sql(query)``"""
            return spark.sql(query)

        namespace.update({"spark": spark, "sc": sc, "sql": sql})

        init_thread.start()

    elif cluster_type == "dask":
        import dask_yarn

        cluster = dask_yarn.YarnCluster.from_current()
        namespace.update({"cluster": cluster})
    elif cluster_type != "none":
        raise RuntimeError("Unknown cluster_type: %r" % cluster_type)


class WaitingForSparkSessionToBeInitialized:
    """Wrapper object for SparkContext and other Spark session variables while the real Spark session is being
    initialized in a background thread. The class name is intentionally worded verbosely explicit as it will show up
    when executing a cell that contains only a Spark session variable like ``sc``.
    """

    # private and public attributes that show up for tab completion,
    # to indicate pending initialization of Spark session
    _WAITING_FOR_SPARK_SESSION_TO_BE_INITIALIZED = "Spark Session not yet initialized ..."
    WAITING_FOR_SPARK_SESSION_TO_BE_INITIALIZED = "Spark Session not yet initialized ..."

    # the same wrapper class is used for all Spark session variables, so we need to record the name of the variable
    def __init__(self, global_variable_name: str, init_thread: Thread, namespace: dict):
        self._spark_session_variable = global_variable_name
        self._init_thread = init_thread
        self._namespace = namespace

    # we intercept all method and attribute references on our temporary Spark session variable,
    # wait for the thread to complete initializing the Spark sessions and then we forward the
    # call to the real Spark objects
    def __getattr__(self, name: str):
        # ignore tab-completion request for __members__ or __methods__ and ignore meta property requests
        if name.startswith("__") or name.startswith("_ipython_") or name.startswith("_repr_"):
            return
        else:
            # wait on thread to initialize the Spark session variables in global variable scope
            self._init_thread.join(timeout=None)
            exc = self._init_thread.exc
            if exc:
                err_msg = f"Variable: {self._spark_session_variable} was not initialized properly."
                raise RuntimeError(err_msg) from exc

            # now return attribute/function reference from actual Spark object
            return getattr(self._namespace[self._spark_session_variable], name)


def _validate_port_range(port_range: Optional[str]) -> tuple[int, int]:
    # if no argument was provided, return a range of 0
    if not port_range:
        return 0, 0

    try:
        port_ranges = port_range.split("..")
        lower_port = int(port_ranges[0])
        upper_port = int(port_ranges[1])

        port_range_size = upper_port - lower_port
        if port_range_size != 0:
            if port_range_size < min_port_range_size:
                err_msg = (
                    f"Port range validation failed for range: '{port_range}'.  Range size must be at least "
                    f"{min_port_range_size} as specified by env MIN_PORT_RANGE_SIZE"
                )
                raise RuntimeError(err_msg)
    except ValueError as ve:
        err_msg = f"Port range validation failed for range: '{port_range}'.  Error was: {ve}"
        raise RuntimeError(err_msg) from ve
    except IndexError as ie:
        err_msg = f"Port range validation failed for range: '{port_range}'.  Error was: {ie}"
        raise RuntimeError(err_msg) from ie

    return lower_port, upper_port


def determine_connection_file(kid: str) -> str:
    # Create a temporary (and empty) file using kernel-id
    fd, conn_file = tempfile.mkstemp(suffix=".json", prefix=f"kernel-{kid}_")
    os.close(fd)
    __logger.debug(f"Using connection file '{conn_file}'.")

    return conn_file


def cancel_spark_jobs(sig: int, frame: Any) -> None:
    if __spark_context is None:
        return
    try:
        __spark_context.cancelAllJobs()
    except Exception as e:
        if e.__class__.__name__ == "Py4JError":
            try:
                __spark_context.cancelAllJobs()
            except Exception as ex:
                __logger.error(
                    f"Error occurred while re-attempting Spark job cancellation when interrupting the kernel: {ex}"
                )
        else:
            __logger.error(
                f"Error occurred while attempting Spark job cancellation when interrupting the kernel: {e}"
            )


def import_item(name: str) -> Any:
    """Import and return ``bar`` given the string ``foo.bar``.
    Calling ``bar = import_item("foo.bar")`` is the functional equivalent of
    executing the code ``from foo import bar``.
    Parameters
    ----------
    name : string
      The fully qualified name of the module/package being imported.
    Returns
    -------
    mod : module object
       The module that was imported.
    """

    parts = name.rsplit(".", 1)
    if len(parts) == 2:
        # called with 'foo.bar....'
        package, obj = parts
        module = __import__(package, fromlist=[obj])
        try:
            pak = getattr(module, obj)
        except AttributeError as ae:
            err_msg = f"No module named '{obj}'"
            raise ImportError(err_msg) from ae
        return pak
    else:
        # called with un-dotted string
        return __import__(parts[0])


def start_ipython(
    namespace: dict,
    cluster_type: str = "spark",
    kernel_class_name: str = DEFAULT_KERNEL_CLASS_NAME,
    **kwargs: Any,
) -> None:
    from ipykernel.kernelapp import IPKernelApp

    # Capture the kernel class before removing 'import_item' from the namespace
    kernel_class = import_item(kernel_class_name)

    # create an initial list of variables to clear
    # we do this without deleting to preserve the locals so that
    # initialize_namespace isn't affected by this mutation
    to_delete = [k for k in namespace if not k.startswith("__")]

    # initialize the namespace with the proper variables
    initialize_namespace(namespace, cluster_type=cluster_type)

    # delete the extraneous variables
    for k in to_delete:
        del namespace[k]

    # Start the kernel.
    app = IPKernelApp.instance(kernel_class=kernel_class, user_ns=namespace, **kwargs)
    app.initialize([])
    app.start()

    # cleanup
    conn_file = kwargs["connection_file"]
    __logger.info(f"IPKernelApp has terminated, removing connection file '{conn_file}'.")
    try:
        import os  # re-import os since it's removed during namespace manipulation during startup

        os.remove(conn_file)
    except Exception as e:
        __logger.error(f"Could not delete connection file '{conn_file}' at exit due to error: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--response-address",
        dest="response_address",
        nargs="?",
        metavar="<ip>:<port>",
        help="Connection address (<ip>:<port>) for returning connection file",
    )
    parser.add_argument(
        "--kernel-id",
        dest="kernel_id",
        nargs="?",
        help="Indicates the id associated with the launched kernel.",
    )
    parser.add_argument(
        "--public-key",
        dest="public_key",
        nargs="?",
        help="Public key used to encrypt connection information",
    )
    parser.add_argument(
        "--port-range",
        dest="port_range",
        nargs="?",
        metavar="<lowerPort>..<upperPort>",
        help="Port range to impose for kernel ports",
    )
    parser.add_argument(
        "--spark-context-initialization-mode",
        dest="init_mode",
        nargs="?",
        default="none",
        help="the initialization mode of the spark context: lazy, eager or none",
    )
    parser.add_argument(
        "--cluster-type",
        dest="cluster_type",
        nargs="?",
        default="spark",
        help="the kind of cluster to initialize: spark, dask, or none",
    )
    parser.add_argument(
        "--kernel-class-name",
        dest="kernel_class_name",
        nargs="?",
        default=DEFAULT_KERNEL_CLASS_NAME,
        help="Indicates the name of the kernel class to use.  Must be a subclass of 'ipykernel.kernelbase.Kernel'.",
    )

    arguments = vars(parser.parse_args())
    response_addr = arguments["response_address"]
    kernel_id = arguments["kernel_id"]
    public_key = arguments["public_key"]
    lower_port, upper_port = _validate_port_range(arguments["port_range"])
    spark_init_mode = arguments["init_mode"]
    cluster_type = arguments["cluster_type"]
    kernel_class_name = arguments["kernel_class_name"]
    ip = "0.0.0.0"  # noqa: S104

    if kernel_id is None:
        err_msg = "Parameter '--kernel-id' must be provided!"
        raise RuntimeError(err_msg)

    if response_addr is None:
        err_msg = "Parameter '--response-address' must be provided!"
        raise RuntimeError(err_msg)

    if public_key is None:
        err_msg = "Parameter '--public-key' must be provided!"
        raise RuntimeError(err_msg)

    # Initialize the kernel namespace for the given cluster type
    if cluster_type == "spark" and spark_init_mode == "none":
        cluster_type = "none"

    # Create connection information
    connection_file = determine_connection_file(kernel_id)

    setup_server_listener(
        connection_file,
        os.getpid(),
        lower_port,
        upper_port,
        response_addr,
        kernel_id,
        public_key,
        cluster_type,
    )

    # setup sig handler to cancel spark jobs on interrupts
    if cluster_type == "spark":
        signal.signal(signal.SIGUSR2, cancel_spark_jobs)

    # launch the IPython kernel instance
    start_ipython(
        locals(),
        cluster_type=cluster_type,
        connection_file=connection_file,
        ip=ip,
        kernel_class_name=kernel_class_name,
    )
