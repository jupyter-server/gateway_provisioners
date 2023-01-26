# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Code related to managing kernels running in YARN clusters."""
import asyncio
import errno
import logging
import os
import signal
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

from overrides import overrides
from traitlets import Bool, Unicode, default

try:
    from yarn_api_client.resource_manager import ResourceManager
except ImportError:
    logging.warning(
        "The extra package 'yarn_api_client'is not installed in this environment and is "
        "required.  Ensure that gateway_provisioners is installed by specifying the "
        "extra 'yarn' (e.g., pip install 'gateway_provisioners[yarn]')."
    )
    raise

from .config_mixin import max_poll_attempts, poll_interval
from .remote_provisioner import RemoteProvisionerBase

# Default logging level of yarn-api and underlying connection pool produce too much noise - raise to warning only.
logging.getLogger("yarn_api_client").setLevel(os.getenv("GP_YARN_LOG_LEVEL", logging.WARNING))
logging.getLogger("urllib3.connectionpool").setLevel(
    os.environ.get("GP_YARN_LOG_LEVEL", logging.WARNING)
)

yarn_shutdown_wait_time = float(os.getenv("GP_YARN_SHUTDOWN_WAIT_TIME", "15.0"))
# cert_path: Boolean, defaults to `True`, that controls
#            whether we verify the server's TLS certificate in yarn-api-client.
#            Or a string, in which case it must be a path to a CA bundle(.pem file) to use.
cert_path = os.getenv("GP_YARN_CERT_BUNDLE", True)


class YarnProvisioner(RemoteProvisionerBase):
    """
    Kernel lifecycle management for YARN clusters.
    """

    yarn_endpoint_env = "GP_YARN_ENDPOINT"
    yarn_endpoint = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""The http url specifying the YARN Resource Manager. Note: If this value is NOT set,
                            the YARN library will use the files within the local HADOOP_CONFIG_DIR to determine the
                            active resource manager. (GP_YARN_ENDPOINT env var)""",
    )

    @default("yarn_endpoint")
    def _yarn_endpoint_default(self):
        return os.getenv(self.yarn_endpoint_env)

    # Alt Yarn endpoint
    alt_yarn_endpoint_env = "GP_ALT_YARN_ENDPOINT"
    alt_yarn_endpoint = Unicode(
        None,
        config=True,
        allow_none=True,
        help="""The http url specifying the alternate YARN Resource Manager.  This value should
                                be set when YARN Resource Managers are configured for high availability.  Note: If both
                                YARN endpoints are NOT set, the YARN library will use the files within the local
                                HADOOP_CONFIG_DIR to determine the active resource manager.
                                (GP_ALT_YARN_ENDPOINT env var)""",
    )

    @default("alt_yarn_endpoint")
    def _alt_yarn_endpoint_default(self):
        return os.getenv(self.alt_yarn_endpoint_env)

    yarn_endpoint_security_enabled_env = "GP_YARN_ENDPOINT_SECURITY_ENABLED"
    yarn_endpoint_security_enabled_default_value = False
    yarn_endpoint_security_enabled = Bool(
        yarn_endpoint_security_enabled_default_value,
        config=True,
        help="""Is YARN Kerberos/SPNEGO Security enabled (True/False).
                                          (GP_YARN_ENDPOINT_SECURITY_ENABLED env var)""",
    )

    @default("yarn_endpoint_security_enabled")
    def _yarn_endpoint_security_enabled_default(self):
        return bool(
            os.getenv(
                self.yarn_endpoint_security_enabled_env,
                self.yarn_endpoint_security_enabled_default_value,
            )
        )

    # Impersonation enabled
    impersonation_enabled_env = "GP_IMPERSONATION_ENABLED"
    impersonation_enabled = Bool(
        False,
        config=True,
        help="""Indicates whether impersonation will be performed during kernel launch.
                                 (GP_IMPERSONATION_ENABLED env var)""",
    )

    @default("impersonation_enabled")
    def _impersonation_enabled_default(self):
        return bool(os.getenv(self.impersonation_enabled_env, "false").lower() == "true")

    initial_states = {"NEW", "SUBMITTED", "ACCEPTED", "RUNNING"}
    final_states = {"FINISHED", "KILLED", "FAILED"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.application_id = None
        self.last_known_state = None
        self.candidate_queue = None
        self.candidate_partition = None

        # If yarn resource check is enabled, and it isn't available immediately,
        # 20% of kernel_launch_timeout is used to wait
        # and retry at fixed interval before pronouncing as not feasible to launch.
        self.yarn_resource_check_wait_time = 0.20 * self.launch_timeout

    @property
    @overrides
    def has_process(self) -> bool:
        return self.local_proc is not None or self.application_id is not None

    @overrides
    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        self.application_id = None
        self.last_known_state = None
        self.candidate_queue = None
        self.candidate_partition = None

        # Transfer impersonation enablement to env.  It is assumed that the kernelspec
        # logic will take the appropriate steps to impersonate the user identified by
        # KERNEL_USERNAME when impersonation_enabled is True.
        env_dict = kwargs.get("env")
        env_dict["GP_IMPERSONATION_ENABLED"] = str(self.impersonation_enabled)

        kwargs = await super().pre_launch(**kwargs)

        self._initialize_resource_manager(**kwargs)

        # checks to see if the queue resource is available
        # if not available, kernel startup is not attempted
        self._confirm_yarn_queue_availability(**kwargs)

        return kwargs

    @overrides
    def get_shutdown_wait_time(self, recommended: Optional[float] = 5.0) -> float:
        # YARN applications tend to take longer than the default 5 second wait time.  Rather than
        # require a command-line option for those using YARN, we'll adjust based on a local env that
        # defaults to 15 seconds.  Note: we'll only adjust if the current wait time is shorter than
        # the desired value.
        if recommended < yarn_shutdown_wait_time:
            recommended = yarn_shutdown_wait_time
            self.log.debug(
                f"{type(self).__name__} shutdown wait time adjusted to {recommended} seconds."
            )

        return recommended

    @overrides
    async def poll(self) -> Optional[int]:
        # Submitting a new kernel/app to YARN will take a while to be ACCEPTED.
        # Thus application ID will probably not be available immediately for poll.
        # So will regard the application as RUNNING when application ID still in ACCEPTED or SUBMITTED state.

        result = 0

        if self._get_application_id():
            state = self._query_app_state_by_id(self.application_id)
            if state in YarnProvisioner.initial_states:
                result = None

        # The following produces too much output (every 3 seconds by default), so commented-out at this time.
        # self.log.debug("YarnProcessProxy.poll, application ID: {}, kernel ID: {}, state: {}".
        #               format(self.application_id, self.kernel_id, state))
        return result

    @overrides
    async def send_signal(self, signum: int) -> None:
        if signum == 0:
            return await self.poll()
        elif signum == signal.SIGKILL:
            return await self.kill()
        else:
            # Yarn api doesn't support the equivalent to interrupts, so take our chances
            # via a remote signal.  Note that this condition cannot check against the
            # signum value because alternate interrupt signals might be in play.
            return await super().send_signal(signum)

    @overrides
    async def kill(self, restart: bool = False) -> None:
        state = None
        result = False
        if self._get_application_id():
            result, state = await self._shutdown_application()

        if result is False:  # We couldn't terminate via Yarn, try remote signal
            result = await super().send_signal(signal.SIGKILL)  # Must use super here, else infinite

        self.log.debug(
            f"YarnProvisioner.kill, application ID: {self.application_id}, "
            f"kernel ID: {self.kernel_id}, state: {state}, result: {result}"
        )
        return result

    @overrides
    async def terminate(self, restart: bool = False) -> None:
        state = None
        result = False
        if self._get_application_id():
            result, state = await self._shutdown_application()

        self.log.debug(
            f"YarnProvisioner.terminate, application ID: {self.application_id}, "
            f"kernel ID: {self.kernel_id}, state: {state}, result: {result}"
        )
        return result

    @overrides
    async def cleanup(self, restart: bool = False) -> None:
        # we might have a defunct process (if using waitAppCompletion = false) - so poll, kill, wait when we have
        # a local_proc.
        if self.local_proc:
            self.log.debug(
                f"YarnProvisioner.cleanup: Clearing possible defunct "
                f"process, pid={self.local_proc.pid}..."
            )

            if self.local_proc.poll():
                self.local_proc.kill()
            self.local_proc.wait()
            self.local_proc = None

        # reset application id to force new query - handles kernel restarts/interrupts
        self.application_id = None

        # for cleanup, we should call the superclass last
        await super().cleanup(restart=restart)

    @overrides
    async def get_provisioner_info(self) -> Dict[str, Any]:
        provisioner_info = await super().get_provisioner_info()
        provisioner_info.update({"application_id": self.application_id})
        return provisioner_info

    @overrides
    async def load_provisioner_info(self, provisioner_info: dict) -> None:
        await super().load_provisioner_info(provisioner_info)
        self.application_id = provisioner_info.get("application_id")

    @overrides
    async def confirm_remote_startup(self) -> None:
        self.start_time = RemoteProvisionerBase.get_current_time()
        i = 0
        ready_to_connect = False  # we're ready to connect when we have a connection file to use
        while not ready_to_connect:
            i += 1
            await self.handle_launch_timeout()

            if self._get_application_id(True):
                # Once we have an application ID, start monitoring state, obtain assigned host and get connection info
                app_state = self._get_application_state()

                if app_state in YarnProvisioner.final_states:
                    error_message = (
                        f"KernelID: '{self.kernel_id}', ApplicationID: '{self.application_id}' "
                        f"unexpectedly found in state '{app_state}' during kernel startup!"
                    )
                    self.log_and_raise(RuntimeError(error_message))

                self.log.debug(
                    f"{i}: State: '{app_state}', Host: '{self.assigned_host}', "
                    f"KernelID: '{self.kernel_id}', ApplicationID: '{self.application_id}'"
                )

                if self.assigned_host != "":
                    ready_to_connect = await self.receive_connection_info()
            else:
                self.detect_launch_failure()

    @overrides
    def log_kernel_launch(self, cmd: List[str]) -> None:
        self.log.info(
            f"{self.__class__.__name__}: kernel launched. YARN RM: {self.rm_addr}, "
            f"pid: {self.local_proc.pid}, Kernel ID: {self.kernel_id}, cmd: '{cmd}'"
        )

    @overrides
    async def handle_launch_timeout(self) -> None:
        """
        Checks to see if the kernel launch timeout has been exceeded while awaiting connection info.

        Note: This is a complete override of the superclass method.
        """
        await asyncio.sleep(poll_interval)
        time_interval = RemoteProvisionerBase.get_time_diff(self.start_time)

        if time_interval > self.launch_timeout:
            reason = (
                f"Application ID is None. Failed to submit a new application to YARN within "
                f"{self.launch_timeout} seconds.  Check server log for more information."
            )

            if self._get_application_id(True):
                if self._query_app_state_by_id(self.application_id) != "RUNNING":
                    reason = (
                        f"YARN resources unavailable after {time_interval} seconds for "
                        f"app {self.application_id}, launch timeout: {self.launch_timeout}!  "
                        "Check YARN configuration."
                    )
                else:
                    reason = (
                        f"App {self.application_id} is RUNNING, but waited too long "
                        f"({self.launch_timeout} secs) to get connection file.  "
                        f"Check YARN logs for more information."
                    )
            await self.kill()
            timeout_message = f"KernelID: '{self.kernel_id}' launch timeout due to: {reason}"
            self.log_and_raise(TimeoutError(timeout_message))

    async def _shutdown_application(self) -> Tuple[Optional[bool], str]:
        """Shuts down the YARN application, returning None if final state is confirmed, False otherwise."""
        result = False
        self._kill_app_by_id(self.application_id)
        # Check that state has moved to a final state (most likely KILLED)
        i = 1
        state = self._query_app_state_by_id(self.application_id)
        while state not in YarnProvisioner.final_states and i <= max_poll_attempts:
            await asyncio.sleep(poll_interval)
            state = self._query_app_state_by_id(self.application_id)
            i += 1

        if state in YarnProvisioner.final_states:
            result = None

        return result, state

    def _confirm_yarn_queue_availability(self, **kwargs: Dict[str, Any]) -> None:
        """
        Submitting jobs to yarn queue and then checking till the jobs are in running state
        will lead to orphan jobs being created in some scenarios.

        We take kernel_launch_timeout time and divide this into two parts.
        If the queue is unavailable we take max 20% of the time to poll the queue periodically
        and if the queue becomes available the rest of timeout is met in 80% of the remaining
        time.

        This algorithm is subject to change. Please read the below cases to understand
        when and how checks are applied.

        Confirms if the yarn queue has capacity to handle the resource requests that
        will be sent to it.

        First check ensures the driver and executor memory request falls within
        the container size of yarn configuration. This check requires executor and
        driver memory to be available in the env.

        Second,Current version of check, takes into consideration node label partitioning
        on given queues. Provided the queue name and node label this checks if
        the given partition has capacity available for kernel startup.

        All Checks are optional. If we have KERNEL_EXECUTOR_MEMORY and KERNEL_DRIVER_MEMORY
        specified, first check is performed.

        If we have KERNEL_QUEUE and KERNEL_NODE_LABEL specified, second check is performed.

        Proper error messages are sent back for user experience
        :param kwargs:
        :return:
        """
        env_dict = kwargs.get("env", {})

        executor_memory = int(env_dict.get("KERNEL_EXECUTOR_MEMORY", 0))
        driver_memory = int(env_dict.get("KERNEL_DRIVER_MEMORY", 0))

        if executor_memory * driver_memory > 0:
            container_memory = self.resource_mgr.cluster_node_container_memory()
            if max(executor_memory, driver_memory) > container_memory:
                self.log_and_raise(
                    ValueError("Container Memory not sufficient for a executor/driver allocation")
                )

        candidate_queue_name = env_dict.get("KERNEL_QUEUE", None)
        node_label = env_dict.get("KERNEL_NODE_LABEL", None)
        partition_availability_threshold = float(env_dict.get("YARN_PARTITION_THRESHOLD", 95.0))

        if candidate_queue_name is None or node_label is None:
            return

        # else the resources may or may not be available now. it may be possible that if we wait then the resources
        # become available. start  a timeout process

        self.start_time = RemoteProvisionerBase.get_current_time()
        self.candidate_queue = self.resource_mgr.cluster_scheduler_queue(candidate_queue_name)

        if self.candidate_queue is None:
            self.log.warning(
                f"Queue: {candidate_queue_name} not found in cluster.  "
                "Availability check will not be performed"
            )
            return

        self.candidate_partition = self.resource_mgr.cluster_queue_partition(
            self.candidate_queue, node_label
        )

        if self.candidate_partition is None:
            self.log.debug(
                f"Partition: {node_label} not found in {candidate_queue_name} queue."
                "Availability check will not be performed"
            )
            return

        self.log.debug(
            f"Checking endpoint: {self.yarn_endpoint} if partition: {self.candidate_partition} "
            f"has used capacity <= {partition_availability_threshold}%"
        )

        yarn_available = self.resource_mgr.cluster_scheduler_queue_availability(
            self.candidate_partition, partition_availability_threshold
        )
        if not yarn_available:
            self.log.debug(
                f"Retrying for {self.yarn_resource_check_wait_time} ms since resources are not available"
            )
            while not yarn_available:
                self._handle_yarn_queue_timeout()
                yarn_available = self.resource_mgr.cluster_scheduler_queue_availability(
                    self.candidate_partition, partition_availability_threshold
                )

        # subtracting the total amount of time spent for polling for queue availability
        self.launch_timeout -= RemoteProvisionerBase.get_time_diff(self.start_time)

    def _handle_yarn_queue_timeout(self) -> None:
        time.sleep(poll_interval)
        time_interval = RemoteProvisionerBase.get_time_diff(self.start_time)

        if time_interval > self.yarn_resource_check_wait_time:
            reason = f"Yarn Compute Resource is unavailable after {self.yarn_resource_check_wait_time} seconds"
            self.log_and_raise(TimeoutError(reason))

    def _initialize_resource_manager(self, **kwargs: Optional[Dict[str, Any]]) -> None:
        """Initialize the Hadoop YARN Resource Manager instance used for this kernel's lifecycle."""

        endpoints = None
        if self.yarn_endpoint:
            endpoints = [self.yarn_endpoint]

            # Only check alternate if "primary" is set.
            if self.alt_yarn_endpoint:
                endpoints.append(self.alt_yarn_endpoint)

        if self.yarn_endpoint_security_enabled:
            from requests_kerberos import HTTPKerberosAuth

            auth = HTTPKerberosAuth()
        else:
            # If we have the appropriate version of yarn-api-client, use its SimpleAuth class.
            # This allows EG to continue to issue requests against the YARN api when anonymous
            # access is not allowed. (Default is to allow anonymous access.)
            try:
                from yarn_api_client.auth import SimpleAuth

                auth = SimpleAuth(self.kernel_username)
                self.log.debug(
                    f"Using SimpleAuth with '{self.kernel_username}' against endpoints: {endpoints}"
                )
            except ImportError:
                auth = None

        self.resource_mgr = ResourceManager(
            service_endpoints=endpoints, auth=auth, verify=cert_path
        )

        self.rm_addr = self.resource_mgr.get_active_endpoint()

    def _get_application_state(self) -> str:
        """
        Gets the current application state using the application_id already obtained.

        Once the assigned host has been identified, 'amHostHttpAddress' is no longer accessed.
        """
        app_state = self.last_known_state
        app = self._query_app_by_id(self.application_id)
        if app:
            if app.get("state"):
                app_state = app.get("state")
                self.last_known_state = app_state

            if self.assigned_host == "" and app.get("amHostHttpAddress"):
                self.assigned_host = app.get("amHostHttpAddress").split(":")[0]
                # Set the assigned ip to the actual host where the application landed.
                self.assigned_ip = socket.gethostbyname(self.assigned_host)

        return app_state

    def _get_application_id(self, ignore_final_states: bool = False) -> Optional[str]:
        """
        Return the kernel's YARN application ID if available, otherwise None.

        If we're obtaining application_id from scratch, do not consider kernels in final states.
        :param ignore_final_states:
        :returns Optional[str] - the YARN application ID or None if not available
        """
        if not self.application_id:
            app = self._query_app_by_name(self.kernel_id)
            state_condition = True
            if type(app) is dict:
                state = app.get("state")
                self.last_known_state = state

                if ignore_final_states:
                    state_condition = state not in YarnProvisioner.final_states

                if len(app.get("id", "")) > 0 and state_condition:
                    self.application_id = app["id"]
                    time_interval = RemoteProvisionerBase.get_time_diff(self.start_time)
                    self.log.info(
                        f"ApplicationID: '{app['id']}' assigned for KernelID: '{self.kernel_id}', "
                        f"state: {state}, {time_interval} seconds after starting."
                    )
            if not self.application_id:
                self.log.debug(
                    f"ApplicationID not yet assigned for KernelID: '{self.kernel_id}' - retrying..."
                )
        return self.application_id

    def _query_app_by_name(self, kernel_id: str) -> Optional[dict]:
        """
        Retrieve application by using kernel_id as the unique app name.

        With the started_time_begin as a parameter to filter applications started earlier than the target one from YARN.
        When submit a new app, it may take a while for YARN to accept and run and generate the application ID.
        Note: if a kernel restarts with the same kernel id as app name, multiple applications will be returned.
        For now, the app/kernel with the top most application ID will be returned as the target app, assuming the app
        ID will be incremented automatically on the YARN side.

        :param kernel_id: as the unique app name for query
        :return: The JSON object of an application or None on failure
        """
        top_most_app_id = ""
        target_app = None
        try:
            response = self.resource_mgr.cluster_applications(
                started_time_begin=str(self.start_time)
            )
        except OSError as sock_err:
            if sock_err.errno == errno.ECONNREFUSED:
                self.log.warning(
                    f"YARN RM address: '{self.rm_addr}' refused the connection.  "
                    f"Is the resource manager running?"
                )
            else:
                self.log.warning(
                    f"Query for kernel ID '{kernel_id}' failed with exception: "
                    f"{type(sock_err)} - '{sock_err}'.  Continuing..."
                )
        except Exception as e:
            self.log.warning(
                f"Query for kernel ID '{kernel_id}' failed with exception: "
                f"{type(e)} - '{e}'.  Continuing..."
            )
        else:
            data = response.data
            if type(data) is dict and type(data.get("apps")) is dict and "app" in data.get("apps"):
                for app in data["apps"]["app"]:
                    if app.get("name", "").find(kernel_id) >= 0 and app.get("id") > top_most_app_id:
                        target_app = app
                        top_most_app_id = app.get("id")
        return target_app

    def _query_app_by_id(self, app_id: str) -> Optional[dict]:
        """Retrieve an application by application ID.

        :param app_id
        :return: The JSON object of an application or None on failure.
        """
        app = None
        try:
            response = self.resource_mgr.cluster_application(application_id=app_id)
        except Exception as e:
            self.log.warning(
                f"Query for application ID '{app_id}' failed with exception: '{e}'.  Continuing..."
            )
        else:
            data = response.data
            if type(data) is dict and "app" in data:
                app = data["app"]

        return app

    def _query_app_state_by_id(self, app_id: str) -> str:
        """Return the state of an application. If a failure occurs, the last known state is returned.

        :param app_id:
        :return: application state (str)
        """
        state = self.last_known_state
        try:
            response = self.resource_mgr.cluster_application_state(application_id=app_id)
        except Exception as e:
            self.log.warning(
                f"Query for application '{app_id}' state failed with exception: '{e}'.  "
                f"Continuing with last known state = '{state}'..."
            )
        else:
            state = response.data["state"]
            self.last_known_state = state

        return state

    def _kill_app_by_id(self, app_id: str) -> dict:
        """Kill an application. If the app's state is FINISHED or FAILED, it won't be changed to KILLED.

        :param app_id
        :return: The JSON response of killing the application.
        """

        response = {}
        try:
            response = self.resource_mgr.cluster_application_kill(application_id=app_id)
        except Exception as e:
            self.log.warning(
                f"Termination of application '{app_id}' failed with exception: '{e}'.  Continuing..."
            )
        return response
