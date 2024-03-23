# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Kernel managers that operate against a remote process."""
import asyncio
import errno
import getpass
import json
import os
import random
import re
import sys
import time
from abc import abstractmethod
from enum import Enum
from socket import AF_INET, SHUT_WR, SOCK_STREAM, socket, timeout
from typing import Any, Dict, List, Optional, Tuple

import pexpect  # type:ignore[import-untyped]
from jupyter_client import (
    KernelConnectionInfo,
    KernelProvisionerBase,
    launch_kernel,
    localinterfaces,
)
from overrides import overrides
from zmq.ssh import tunnel

from .config_mixin import (
    RemoteProvisionerConfigMixin,
    max_poll_attempts,
    poll_interval,
    socket_timeout,
    ssh_port,
)
from .response_manager import ResponseManager

# Pop certain env variables that don't need to be logged, e.g. remote_pwd
env_pop_list = ["GP_REMOTE_PWD", "LS_COLORS"]
default_kernel_launch_timeout = float(os.getenv("KERNEL_LAUNCH_TIMEOUT", "30"))

# Minimum port range size and max retries
min_port_range_size = int(os.getenv("GP_MIN_PORT_RANGE_SIZE", "1000"))
max_port_range_retries = int(os.getenv("GP_MAX_PORT_RANGE_RETRIES", "5"))

# Number of seconds in 100 years as the max keep-alive interval value.
max_keep_alive_interval_default = 100 * 365 * 24 * 60 * 60
max_keep_alive_interval = int(
    os.getenv("GP_TUNNEL_MAX_KEEP_ALIVE", max_keep_alive_interval_default)
)

tunneling_enabled = bool(os.getenv("GP_ENABLE_TUNNELING", "False").lower() == "true")

local_ip = localinterfaces.public_ips()[0]

random.seed()


class KernelChannel(Enum):
    """Enumeration used to better manage tunneling"""

    SHELL = "SHELL"
    IOPUB = "IOPUB"
    STDIN = "STDIN"
    HEARTBEAT = "HB"
    CONTROL = "CONTROL"
    COMMUNICATION = (
        "GP_COMM"  # Optional channel for remote launcher to issue interrupts - NOT a ZMQ channel
    )


def gp_launch_kernel(cmd: list, **kwargs):
    return launch_kernel(cmd, **kwargs)


class RemoteProvisionerBase(RemoteProvisionerConfigMixin, KernelProvisionerBase):
    """Base class for remote provisioners."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.start_time = None
        self.assigned_ip = None
        self.assigned_host = ""
        self.comm_ip = None
        self.comm_port = 0
        self.kernel_username = None
        self.tunneled_connect_info = None
        self.tunnel_processes = {}

        # Represents the local process (from popen) if applicable.  This will likely be non-None
        # for a short while until the script has launched the remote process, then will typically
        # go away.
        self.local_proc = None
        self.ip = None
        self.pid = 0
        self.pgid = 0

        self.response_manager = (
            ResponseManager.instance()
        )  # This will create the key pair and socket on first use
        self.response_address = self.response_manager.response_address
        self.public_key = self.response_manager.public_key
        self.lower_port, self.upper_port = self._validate_port_range()

    @property
    @abstractmethod
    @overrides
    def has_process(self) -> bool:
        pass

    @overrides
    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        self.response_manager.register_event(self.kernel_id)

        cmd = self.kernel_spec.argv  # Build launch command, provide substitutions
        if self.response_address or self.port_range or self.kernel_id or self.public_key:
            ns = kwargs.copy()
            if self.response_address:
                ns["response_address"] = self.response_address
            if self.public_key:
                ns["public_key"] = self.public_key
            if self.port_range:
                ns["port_range"] = self.port_range
            if self.kernel_id:
                ns["kernel_id"] = self.kernel_id

            pat = re.compile(r"{([A-Za-z0-9_]+)}")

            def from_ns(match):
                """Get the key out of ns if it's there, otherwise no change."""
                return ns.get(match.group(1), match.group())

            cmd = [pat.sub(from_ns, arg) for arg in cmd]

        kwargs = await super().pre_launch(cmd=cmd, **kwargs)

        env = kwargs.get("env", {})
        self.kernel_username = env.get("KERNEL_USERNAME", getpass.getuser())  # Let env override
        env["KERNEL_USERNAME"] = self.kernel_username  # reset in env in case it's not there

        self._enforce_authorization(**kwargs)

        self.log.debug(f"RemoteProvisionerBase.pre_launch() env: {env}")
        return kwargs

    @overrides
    async def launch_kernel(self, cmd: List[str], **kwargs: Any) -> KernelConnectionInfo:
        launch_kwargs = RemoteProvisionerBase._scrub_kwargs(kwargs)
        self.log.debug(f"RemoteProvisionerBase.launch_kernel() env: {launch_kwargs.get('env', {})}")
        self.local_proc = gp_launch_kernel(cmd, **launch_kwargs)
        self.pid = self.local_proc.pid
        self.ip = local_ip

        self.log_kernel_launch(cmd)

        await self.confirm_remote_startup()
        return self.connection_info

    @overrides
    async def post_launch(self, **kwargs: Any) -> None:
        pass

    @abstractmethod
    @overrides
    async def poll(self) -> Optional[int]:
        pass

    @overrides
    async def wait(self) -> Optional[int]:
        # If we have a local_proc, call its wait method.  This will cleanup any defunct processes when the kernel
        # is shutdown (when using waitAppCompletion = false).  Otherwise (if no local_proc) we'll use polling to
        # determine if a (remote or revived) process is still active.
        if self.local_proc:
            return self.local_proc.wait()

        poll_val = 0
        for _i in range(max_poll_attempts):
            poll_val = await self.poll()
            if poll_val is None:
                await asyncio.sleep(poll_interval)
            else:
                break
        else:
            self.log.warning(
                "Wait timeout of {} seconds exhausted. Continuing...".format(
                    max_poll_attempts * poll_interval
                )
            )
        return poll_val

    @overrides
    async def send_signal(self, signum: int) -> None:
        await self._send_signal_via_listener(signum)

    @abstractmethod
    @overrides
    async def kill(self, restart: bool = False) -> None:
        pass

    @abstractmethod
    @overrides
    async def terminate(self, restart: bool = False) -> None:
        pass

    @overrides
    async def cleanup(self, restart: bool = False) -> None:
        self.assigned_ip = None

        for kernel_channel, process in self.tunnel_processes.items():
            self.log.debug(f"cleanup: terminating {kernel_channel} tunnel process.")
            process.terminate()

        self.tunnel_processes.clear()

    @overrides
    async def shutdown_requested(self, restart: bool = False) -> None:
        await self.shutdown_listener(restart)

    @overrides
    async def get_provisioner_info(self) -> Dict[str, Any]:
        provisioner_info = await super().get_provisioner_info()
        provisioner_info.update(
            {
                "pid": self.pid,
                "pgid": self.pgid,
                "ip": self.ip,
                "assigned_ip": self.assigned_ip,
                "assigned_host": self.assigned_host,
                "comm_ip": self.comm_ip,
                "comm_port": self.comm_port,
                "tunneled_connect_info": self.tunneled_connect_info,
            }
        )
        return provisioner_info

    @overrides
    async def load_provisioner_info(self, provisioner_info: dict) -> None:
        await super().load_provisioner_info(provisioner_info)
        self.pid = provisioner_info.get("pid")
        self.pgid = provisioner_info.get("pgid")
        self.ip = provisioner_info.get("ip")
        self.assigned_ip = provisioner_info.get("assigned_ip")
        self.assigned_host = provisioner_info.get("assigned_host")
        self.comm_ip = provisioner_info.get("comm_ip")
        self.comm_port = provisioner_info.get("comm_port")
        self.tunneled_connect_info = provisioner_info.get("tunneled_connect_info")

    @overrides
    def get_shutdown_wait_time(self, recommended: float = 5.0) -> float:  # type;ignore[override]
        return recommended

    @overrides
    def _finalize_env(self, env: Dict[str, str]) -> None:
        # add the applicable kernel_id and language to the env dict
        env["KERNEL_ID"] = self.kernel_id

        kernel_language = "unknown-kernel-language"
        if len(self.kernel_spec.language) > 0:
            kernel_language = self.kernel_spec.language.lower()
        # if already set in env: stanza, let that override.
        env["KERNEL_LANGUAGE"] = env.get("KERNEL_LANGUAGE", kernel_language)

        # Remove any potential sensitive (e.g., passwords) or annoying values (e.g., LG_COLORS)
        for k in env_pop_list:
            env.pop(k, None)

    @staticmethod
    def _scrub_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Remove any keyword arguments that Popen does not tolerate."""
        keywords_to_scrub: List[str] = ["extra_arguments", "kernel_id"]
        scrubbed_kwargs = kwargs.copy()
        for kw in keywords_to_scrub:
            scrubbed_kwargs.pop(kw, None)

        return scrubbed_kwargs

    @abstractmethod
    def log_kernel_launch(self, cmd: List[str]) -> None:
        """Logs the kernel launch from the respective remote provisioner"""
        pass

    async def handle_launch_timeout(self):
        """
        Checks to see if the kernel launch timeout has been exceeded while awaiting connection info.
        """
        await asyncio.sleep(poll_interval)
        time_interval = RemoteProvisionerBase.get_time_diff(
            self.start_time  # type:ignore[arg-type]
        )

        if time_interval > self.launch_timeout:
            reason = f"Waited too long ({self.launch_timeout}s) to get connection file"
            timeout_message = f"KernelID: '{self.kernel_id}' launch timeout due to: {reason}"
            await self.kill()
            self.log_and_raise(TimeoutError(timeout_message))

    @abstractmethod
    async def confirm_remote_startup(self):
        """Confirms the remote process has started and returned necessary connection information."""
        pass

    def detect_launch_failure(self):
        """
        Helper method called from implementations of `confirm_remote_startup()` that checks if
        self.local_proc (a popen instance) has terminated prior to the confirmation of startup.
        This prevents users from having to wait for the kernel timeout duration to know if the
        launch fails.  It also helps distinguish local invocation issues from remote post-launch
        issues since the failure will be relatively immediate.

        Note that this method only applies to those process proxy implementations that launch
        from the local node.  Proxies like DistributedProcessProxy use rsh against a remote
        node, so there's not `local_proc` in play to interrogate.
        """

        # Check if the local proc has faulted (poll() will return non-None with a non-zero return
        # code in such cases).  If a fault was encountered, raise server error (500) with a message
        # indicating to check the EG log for more information.
        if self.local_proc:
            poll_result = self.local_proc.poll()
            if poll_result and poll_result > 0:
                self.local_proc.wait()  # FIXME
                error_message = (
                    f"Error occurred during launch of KernelID: {self.kernel_id}.  "
                    "Check Enterprise Gateway log for more information."
                )
                self.local_proc = None
                self.log_and_raise(RuntimeError(error_message))

    def log_and_raise(self, ex: Exception, chained: Optional[Exception] = None) -> None:
        """Helper method that logs the string-ized exception 'ex' and raises that exception.

        If a chained exception is provided that exception will be in the raised exception's from clause.

        :param ex : Exception
            The exception to log and raise
        :param chained : Exception (optional)
            The exception to use in the 'from' clause.
        """

        self.log.error(str(ex))
        if chained:
            raise ex from chained
        else:
            raise ex

    async def shutdown_listener(self, restart: bool) -> None:
        """
        Sends a shutdown request to the kernel launcher listener.
        """
        # If a comm port has been established, instruct the listener to shutdown so that proper
        # kernel termination can occur.  If not done, the listener keeps the launcher process
        # active, even after the kernel has terminated, leading to less than graceful terminations.

        if self.comm_port > 0:
            try:
                await self._send_listener_request({"shutdown": 1}, shutdown_socket=True)
                self.log.debug("Shutdown request sent to listener via gateway communication port.")
            except Exception as e:
                if not isinstance(e, OSError) or e.errno != errno.ECONNREFUSED:
                    self.log.warning(
                        f"An unexpected exception occurred sending listener shutdown "
                        f"to {self.comm_ip}:{self.comm_port} for "
                        f"KernelID '{self.kernel_id}': {e}"
                    )

            # Also terminate the tunnel process for the communication port - if in play.  Failure to terminate
            # this process results in the kernel (launcher) appearing to remain alive following the shutdown
            # request, which triggers the "forced kill" termination logic.

            comm_port_name = KernelChannel.COMMUNICATION.value
            comm_port_tunnel = self.tunnel_processes.get(comm_port_name, None)
            if comm_port_tunnel:
                self.log.debug(f"shutdown_listener: terminating {comm_port_name} tunnel process.")
                comm_port_tunnel.terminate()
                del self.tunnel_processes[comm_port_name]

    async def receive_connection_info(self) -> bool:
        """
        Monitors the response address for connection info sent by the remote kernel launcher.
        """
        # Polls the socket using accept.  When data is found, returns ready indicator and encrypted data.
        ready_to_connect = False
        try:
            connect_info = await self.response_manager.get_connection_info(self.kernel_id)
            self._setup_connection_info(connect_info)
            ready_to_connect = True
        except Exception as e:
            if (
                type(e) is timeout
                or type(e) is TimeoutError
                or type(e) is asyncio.exceptions.TimeoutError
            ):
                self.log.debug(
                    f"Waiting for KernelID '{self.kernel_id}' to send connection "
                    f"info from host '{self.assigned_host}' - retrying..."
                )
            else:
                error_message = (
                    f"Exception occurred waiting for connection file response for "
                    f"KernelId '{self.kernel_id}' on host '{self.assigned_host}': {e}"
                )
                await self.kill()
                self.log_and_raise(RuntimeError(error_message), chained=e)

        return ready_to_connect

    @staticmethod
    def get_current_time() -> int:
        """Return the current time (in milliseconds) from epoch.

        This method is intended for use in determining timeout values.
        """
        float_time = time.time()
        return int(float_time * 1000)  # Convert to ms and int

    @staticmethod
    def get_time_diff(start_time_ms: int) -> float:
        """Return the difference (in seconds) between the given start_time and the current time"""
        end_time_ms = RemoteProvisionerBase.get_current_time()
        time_diff = float((end_time_ms - start_time_ms) / 1000)
        return time_diff

    @staticmethod
    def ip_is_local(ip):
        """Returns True if `ip` is considered local to this server, False otherwise."""
        return localinterfaces.is_public_ip(ip) or localinterfaces.is_local_ip(ip)

    async def _send_signal_via_listener(self, signum: int) -> bool:
        """Sends signal 'signum' to kernel process via listener.

        :returns: True if request delivered, false otherwise.
        """
        # If the launcher returned a comm_port value, then use that to send the signal,
        # else, defer to the superclass - which will use a remote shell to issue kill.
        # Note that if the target process is running as a different user than the REMOTE_USER,
        # using anything other than the socket-based signal (via signal_addr) will not work.
        if self.comm_port > 0:
            try:
                await self._send_listener_request({"signum": signum})
                if signum > 0:  # Polling (signum == 0) is too frequent
                    self.log.debug(f"Signal ({signum}) sent via gateway communication port.")
                return True
            except Exception as e:
                if (
                    isinstance(e, OSError) and e.errno == errno.ECONNREFUSED
                ):  # Return False since there's no process.
                    if (
                        signum > 0
                    ):  # Since poll's purpose is to check status, consider this as terminated.
                        self.log.debug(
                            "ERROR: ECONNREFUSED, no process listening, cannot send signal."
                        )
                else:
                    self.log.warning(
                        f"An unexpected exception occurred sending signal ({signum}) "
                        f"via listener for KernelID '{self.kernel_id}': {e}"
                    )
        return False

    def _enforce_authorization(self, **kwargs):
        """Applies any authorization configuration using the kernel user.

        Authorization is performed by comparing the value of KERNEL_USERNAME with each value in the set of
        unauthorized users.  If any (case-sensitive) matches are found, HTTP error 403 (Forbidden) will be raised
        - preventing the launch of the kernel.  If the authorized_users set is non-empty, it is then checked to
        ensure the value of KERNEL_USERNAME is present in that list.  If not found, HTTP error 403 will be raised.

        """

        # Now perform authorization checks
        if self.kernel_username in self.unauthorized_users:
            self._raise_authorization_error("not authorized")

        # If authorized users are non-empty, ensure user is in that set.
        if self.authorized_users.__len__() > 0:
            if self.kernel_username not in self.authorized_users:
                self._raise_authorization_error("not in the set of users authorized")

    def _raise_authorization_error(self, differentiator_clause):
        """Raises a 403 status code after building the appropriate message."""
        kernel_name = self.kernel_spec.display_name
        kernel_clause = f" '{kernel_name}'." if kernel_name is not None else "s."
        error_message = (
            f"User '{self.kernel_username}' is {differentiator_clause} to start kernel{kernel_clause} "
            "Ensure KERNEL_USERNAME is set to an appropriate value and retry the request."
        )
        self.log_and_raise(PermissionError(error_message))

    def _validate_port_range(self) -> Tuple[int, int]:
        """Validates the port range configuration option to ensure appropriate values."""

        lower_port = upper_port = 0
        port_range = self.port_range
        assert port_range is not None
        try:
            port_ranges = port_range.split("..")

            lower_port = int(port_ranges[0])
            upper_port = int(port_ranges[1])

            port_range_size = upper_port - lower_port
            if port_range_size != 0:
                if port_range_size < min_port_range_size:
                    self.log_and_raise(
                        ValueError(
                            f"Port range validation failed for range: '{port_range}'.  "
                            f"Range size must be at least {min_port_range_size} as "
                            f"specified by env GP_MIN_PORT_RANGE_SIZE"
                        )
                    )

                # According to RFC 793, port is a 16-bit unsigned int. Which means the port
                # numbers must be in the range (0, 65535). However, within that range,
                # ports 0 - 1023 are called "well-known ports" and are typically reserved for
                # specific purposes. For example, 0 is reserved for random port assignment,
                # 80 is used for HTTP, 443 for TLS/SSL, 25 for SMTP, etc. But, there is
                # flexibility as one can choose any port with the aforementioned protocols.
                # Ports 1024 - 49151 are called "user or registered ports" that are bound to
                # services running on the server listening to client connections. And, ports
                # 49152 - 65535 are called "dynamic or ephemeral ports". A TCP connection
                # has two endpoints. Each endpoint consists of an IP address and a port number.
                # And, each connection is made up of a 4-tuple consisting of -- client-IP,
                # client-port, server-IP, and server-port. A service runs on a server with a
                # specific IP and is bound to a specific "user or registered port" that is
                # advertised for clients to connect. So, when a client connects to a service
                # running on a server, three out of 4-tuple - client-IP, client-port, server-IP -
                # are already known. To be able to serve multiple clients concurrently, the
                # server's IP stack assigns an ephemeral port for the connection to complete
                # the 4-tuple.
                #
                # In case of JEG, we will accept ports in the range 1024 - 65535 as these days
                # admins use dedicated hosts for individual services.
                def validate_port(port: int) -> None:
                    if port < 1024 or port > 65535:
                        self.log_and_raise(
                            ValueError(
                                f"Invalid port range '{port_range}' specified. "
                                "Range for valid port numbers is (1024, 65535)."
                            )
                        )

                validate_port(lower_port)
                validate_port(upper_port)
        except IndexError as ie:
            self.log_and_raise(
                RuntimeError(f"Port range validation failed for range: '{port_range}'."),
                chained=ie,
            )

        return lower_port, upper_port

    def _setup_connection_info(self, connect_info: dict) -> None:
        """
        Take connection info (returned from launcher or loaded from session persistence) and properly
        configure port variables for the 5 kernel and (possibly) the launcher communication port.  If
        tunneling is enabled, these ports will be tunneled with the original port information recorded.
        """

        self.log.debug(
            f"Host assigned to the kernel is: '{self.assigned_host}' '{self.assigned_ip}'"
        )

        connect_info[
            "ip"
        ] = self.assigned_ip  # Set connection to IP address of system where the kernel was launched

        if tunneling_enabled is True:
            # Capture the current(tunneled) connect_info relative to the IP and ports (including the
            # communication port - if present).
            self.tunneled_connect_info = dict(connect_info)

            # Open tunnels to the 5 ZMQ kernel ports
            assert self.assigned_ip is not None
            tunnel_ports = self._tunnel_to_kernel(connect_info, self.assigned_ip)
            self.log.debug(f"Local ports used to create SSH tunnels: '{tunnel_ports}'")

            # Replace the remote connection ports with the local ports used to create SSH tunnels.
            connect_info["ip"] = "127.0.0.1"
            connect_info["shell_port"] = tunnel_ports[0]
            connect_info["iopub_port"] = tunnel_ports[1]
            connect_info["stdin_port"] = tunnel_ports[2]
            connect_info["hb_port"] = tunnel_ports[3]
            connect_info["control_port"] = tunnel_ports[4]

            # If a communication port was provided, tunnel it
            if "comm_port" in connect_info:
                self.comm_ip = connect_info["ip"]
                tunneled_comm_port = int(connect_info["comm_port"])
                self.comm_port = self._tunnel_to_port(
                    KernelChannel.COMMUNICATION,
                    self.assigned_ip,
                    tunneled_comm_port,
                    self.assigned_ip,
                )
                connect_info["comm_port"] = self.comm_port
                self.log.debug(
                    f"Established communication to: {self.assigned_ip}:{tunneled_comm_port} "
                    f"for KernelID '{self.kernel_id}' via tunneled port 127.0.0.1:{self.comm_port}"
                )

        else:  # tunneling not enabled, still check for and record communication port
            if "comm_port" in connect_info:
                self.comm_ip = connect_info["ip"]
                self.comm_port = int(connect_info["comm_port"])
                self.log.debug(
                    f"Established communication to: {self.assigned_ip}:{self.comm_port} "
                    f"for KernelID '{self.kernel_id}'"
                )

        # If no communication port was provided, record that fact as well since this is useful to know
        if "comm_port" not in connect_info:
            self.log.debug(
                f"Communication port has NOT been established for KernelID '{self.kernel_id}' (optional)."
            )

        self._update_connection(connect_info)

    def _update_connection(self, connect_info: dict) -> None:
        """
        Updates the connection info with that received from launcher.  Also pulls the PID and PGID
        info, if present, in case we need to use it for lifecycle management.
        Note: Do NOT update connect_info with IP and other such artifacts in this method/function.
        """

        if not connect_info:
            error_message = (
                f"Unexpected runtime encountered for Kernel ID '{self.kernel_id}' - "
                f"connection information is null!"
            )
            self.log_and_raise(RuntimeError(error_message))

        # Load new connection information into memory. No need to write back out to a file or track loopback, etc.
        # The launcher may also be sending back process info, so check and extract
        self._extract_pid_info(connect_info)
        self.log.debug(
            f"Received connection info for KernelID '{self.kernel_id}' "
            f"from host '{self.assigned_host}': {connect_info}..."
        )

        self.connection_info.update(connect_info)

    def _extract_pid_info(self, connect_info: dict) -> None:
        """
        Extracts any PID, PGID info from the payload received on the response socket.
        """
        pid = connect_info.pop("pid", None)
        if pid:
            try:
                self.pid = int(pid)
            except ValueError:
                self.log.warning(
                    f"pid returned from kernel launcher is not an integer: {pid} - ignoring."
                )
                pid = None
        pgid = connect_info.pop("pgid", None)
        if pgid:
            try:
                self.pgid = int(pgid)
            except ValueError:
                self.log.warning(
                    f"pgid returned from kernel launcher is not an integer: {pgid} - ignoring."
                )
                pgid = None
        if (
            pid or pgid
        ):  # if either process ids were updated, update the ip as well and don't use local_proc
            self.ip = self.assigned_ip
            if not RemoteProvisionerBase.ip_is_local(
                self.ip
            ):  # only unset local_proc if we're remote
                # FIXME - should we wait prior to unset?
                self.local_proc = None

    async def _send_listener_request(
        self, request: dict, shutdown_socket: Optional[bool] = False
    ) -> None:
        """
        Sends the request dictionary to the kernel listener via the comm port.  Caller is responsible for
        handling any exceptions.
        """
        if self.comm_port > 0:
            sock = socket(AF_INET, SOCK_STREAM)
            try:
                sock.settimeout(socket_timeout)
                await asyncio.get_event_loop().sock_connect(sock, (self.comm_ip, self.comm_port))
                sock.send(json.dumps(request).encode(encoding="utf-8"))
            finally:
                if shutdown_socket:
                    try:
                        sock.shutdown(SHUT_WR)
                    except Exception as e2:
                        issue_warning: bool = True
                        if isinstance(e2, OSError) and e2.errno == errno.ENOTCONN:
                            # Listener is not connected.  This is probably a follow-on to ECONNREFUSED on connect
                            if (
                                "shutdown" in request
                            ):  # If this is a shutdown request, dampen the urgency
                                issue_warning = False
                                self.log.debug(
                                    "OSError(ENOTCONN) raised on socket shutdown, listener likely "
                                    "not connected due to listener's expected termination."
                                )
                        if issue_warning:
                            self.log.warning(
                                f"Exception occurred attempting to shutdown communication "
                                f"socket to {self.comm_ip}:{self.comm_port} for KernelID "
                                f"'{self.kernel_id}' (ignored): {e2!s}"
                            )
                sock.close()
        else:
            self.log.debug(
                "Invalid comm port, not sending request '{}' to comm_port '{}'.",
                request,
                self.comm_port,
            )

    def _tunnel_to_kernel(
        self,
        connection_info: dict,
        server: str,
        port: int = ssh_port,
        key: Optional[str] = None,
    ):
        """
        Tunnel connections to a kernel over SSH

        This will open five SSH tunnels from localhost on this machine to the
        ports associated with the kernel.
        See jupyter_client/connect.py for original implementation.
        """
        cf = connection_info

        lports = self._select_ports(5)

        rports = (
            cf["shell_port"],
            cf["iopub_port"],
            cf["stdin_port"],
            cf["hb_port"],
            cf["control_port"],
        )

        channels = (
            KernelChannel.SHELL,
            KernelChannel.IOPUB,
            KernelChannel.STDIN,
            KernelChannel.HEARTBEAT,
            KernelChannel.CONTROL,
        )

        remote_ip = cf["ip"]

        if not tunnel.try_passwordless_ssh(server + ":" + str(port), key):
            self.log_and_raise(
                PermissionError(
                    "Must use password-less scheme by setting up the "
                    "SSH public key on the cluster nodes"
                )
            )

        for lp, rp, kc in zip(lports, rports, channels):
            self._create_ssh_tunnel(kc, lp, rp, remote_ip, server, port, key)

        return tuple(lports)

    def _tunnel_to_port(
        self,
        kernel_channel: KernelChannel,
        remote_ip: str,
        remote_port: int,
        server: str,
        port: int = ssh_port,
        key: Optional[str] = None,
    ):
        """
        Analogous to _tunnel_to_kernel, but deals with a single port.  This will typically be called for
        any one-off ports that require tunnelling. Note - this method assumes that passwordless ssh is
        in use and has been previously validated.
        """
        local_port = self._select_ports(1)[0]
        self._create_ssh_tunnel(
            kernel_channel, local_port, remote_port, remote_ip, server, port, key
        )
        return local_port

    def _create_ssh_tunnel(
        self,
        kernel_channel: KernelChannel,
        local_port: int,
        remote_port: int,
        remote_ip: str,
        server: str,
        port: int,
        key: Optional[str] = None,
    ):
        """
        Creates an SSH tunnel between the local and remote port/server for the given kernel channel.
        """
        channel_name = kernel_channel.value
        self.log.debug(
            f"Creating SSH tunnel for '{channel_name}': 127.0.0.1:'{local_port}' "
            f"to '{remote_ip}':'{remote_port}'"
        )
        try:
            process = RemoteProvisionerBase._spawn_ssh_tunnel(
                local_port, remote_port, remote_ip, server, port, key
            )
            self.tunnel_processes[channel_name] = process
        except Exception as e:
            self.log_and_raise(
                RuntimeError(
                    f"Could not open SSH tunnel for port {channel_name}. Exception: '{e}'"
                ),
                chained=e,
            )

    @staticmethod
    def _spawn_ssh_tunnel(
        local_port: int,
        remote_port: int,
        remote_ip: str,
        server: str,
        port: int,
        key: Optional[str] = None,
    ):
        """
        This method spawns a child process to create an SSH tunnel and returns the spawned process.
        ZMQ's implementation returns a pid on UNIX based platforms and a process handle/reference on
        Win32. By consistently returning a process handle/reference on both UNIX and Win32 platforms,
        this method enables the caller to deal with the same currency regardless of the platform. For
        example, on both UNIX and Win32 platforms, the developer will have the option to stash the
        child process reference and manage it's lifecycle consistently.

        On UNIX based platforms, ZMQ's implementation is more generic to be able to handle various
        use-cases. ZMQ's implementation also requests the spawned process to go to background using
        '-f' command-line option. As a result, the spawned process becomes an orphan and any references
        to the process obtained using it's pid become stale. On the other hand, this implementation is
        specifically for password-less SSH login WITHOUT the '-f' command-line option thereby allowing
        the spawned process to be owned by the parent process. This allows the parent process to control
        the lifecycle of it's child processes and do appropriate cleanup during termination.
        """
        if sys.platform == "win32":
            ssh_server = server + ":" + str(port)
            return tunnel.paramiko_tunnel(local_port, remote_port, ssh_server, remote_ip, key)
        else:
            ssh = "ssh -p %s -o ServerAliveInterval=%i" % (
                port,
                max_keep_alive_interval,
            )
            cmd = "%s -S none -L 127.0.0.1:%i:%s:%i %s" % (
                ssh,
                local_port,
                remote_ip,
                remote_port,
                server,
            )
            return pexpect.spawn(cmd, env=os.environ.copy().pop("SSH_ASKPASS", None))

    def _select_ports(self, count: int) -> List[int]:
        """
        Selects and returns n random ports that adhere to the configured port range, if applicable.

        Parameters
        ----------
        count : int
            The number of ports to return

        Returns
        -------
        List - ports available and adhering to the configured port range
        """
        ports: List[int] = []
        sockets: List[socket] = []
        for _i in range(count):
            sock = self._select_socket()
            ports.append(sock.getsockname()[1])
            sockets.append(sock)
        for sock in sockets:
            sock.close()
        return ports

    def _select_socket(self, ip: str = "") -> socket:
        """
        Creates and returns a socket whose port adheres to the configured port range, if applicable.

        Parameters
        ----------
        ip : str
            Optional ip address to which the port is bound

        Returns
        -------
        socket - Bound socket that is available and adheres to configured port range
        """
        sock = socket(AF_INET, SOCK_STREAM)
        found_port = False
        retries = 0
        while not found_port:
            try:
                sock.bind((ip, self._get_candidate_port()))
                found_port = True
            except Exception:
                retries = retries + 1
                if retries > max_port_range_retries:
                    self.log_and_raise(
                        RuntimeError(
                            f"Failed to locate port within range {self.port_range} "
                            f"after {max_port_range_retries} retries!"
                        )
                    )
        return sock

    def _get_candidate_port(self):
        """Randomly selects a port number within the configured range.

        If no range is configured, the 0 port is used - allowing the server to choose from the full range.
        """
        range_size = self.upper_port - self.lower_port
        if range_size == 0:
            return 0
        return random.randint(self.lower_port, self.upper_port)
