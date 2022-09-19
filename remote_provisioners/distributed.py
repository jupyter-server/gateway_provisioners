# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Code related to managing kernels running in YARN clusters."""
from __future__ import annotations

import asyncio
import getpass
import json
import os
import paramiko
import signal
import subprocess
import warnings

from socket import gethostbyname, gethostname
from traitlets import default, List, TraitError, Unicode, validate
from typing import Any, Dict, List as tyList, Optional
from jupyter_client import launch_kernel, KernelConnectionInfo

from .config_mixin import poll_interval, max_poll_attempts, ssh_port
from .remote_provisioner import RemoteProvisionerBase

kernel_log_dir = os.getenv("RP_KERNEL_LOG_DIR", '/tmp')  # would prefer /var/log, but its only writable by root


class TrackKernelOnHost:
    """
    Class used to track the number of active kernels on the set of hosts
    so that the least-utilized host can be used for the next distributed
    request.
    """
    _host_kernels = {}
    _kernel_host_mapping = {}

    def add_kernel_id(self, host: str, kernel_id: str) -> None:
        self._kernel_host_mapping[kernel_id] = host
        self.increment(host)

    def delete_kernel_id(self, kernel_id: str) -> None:
        host = self._kernel_host_mapping.get(kernel_id)
        if host:
            self.decrement(host)
            del self._kernel_host_mapping[kernel_id]

    def min_or_remote_host(self, remote_host: str | None = None) -> str:
        if remote_host:
            return remote_host
        return min(self._host_kernels, key=lambda k: self._host_kernels[k])

    def increment(self, host: str) -> None:
        val = int(self._host_kernels.get(host, 0))
        self._host_kernels[host] = val + 1

    def decrement(self, host: str) -> None:
        val = int(self._host_kernels.get(host, 0))
        self._host_kernels[host] = val - 1

    def init_host_kernels(self, hosts) -> None:
        if len(self._host_kernels) == 0:
            self._host_kernels.update({key: 0 for key in hosts})


class DistributedProvisioner(RemoteProvisionerBase):
    """
    Kernel lifecycle management for clusters via ssh and a set of hosts.
    """
    host_index = 0
    kernel_on_host = TrackKernelOnHost()

    remote_hosts_env = 'RP_REMOTE_HOSTS'
    remote_hosts_default_value = 'localhost'
    remote_hosts = List(default_value=[remote_hosts_default_value], config=True,
                        help="""List of host names on which this kernel can be launched.  Multiple entries must
                        each be specified via separate options: --remote-hosts host1 --remote-hosts host2""")

    @default('remote_hosts')
    def remote_hosts_default(self):
        return os.getenv(self.remote_hosts_env, self.remote_hosts_default_value).split(',')

    load_balancing_algorithm_env = "RP_LOAD_BALANCING_ALGORITHM"
    load_balancing_algorithm_default_value = "round-robin"
    load_balancing_algorithm = Unicode(
        load_balancing_algorithm_default_value,
        config=True,
        help="""Specifies which load balancing algorithm DistributedProvisioner should use.
            Must be one of "round-robin" or "least-connection".  (RP_LOAD_BALANCING_ALGORITHM
            env var)
            """,
    )

    @default("load_balancing_algorithm")
    def load_balancing_algorithm_default(self) -> str:
        return os.getenv(
            self.load_balancing_algorithm_env, self.load_balancing_algorithm_default_value
        )

    @validate("load_balancing_algorithm")
    def _validate_load_balancing_algorithm(self, proposal: Dict[str, str]) -> str:
        value = proposal["value"]
        try:
            assert value in ["round-robin", "least-connection"]
        except ValueError:
            raise TraitError(
                f"Invalid load_balancing_algorithm value {value}, not in [round-robin,least-connection]"
            )
        return value

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kernel_log = None
        self.local_stdout = None
        self.least_connection = self.load_balancing_algorithm == "least-connection"
        _remote_user = os.getenv("RP_REMOTE_USER")
        self.remote_pwd = os.getenv("RP_REMOTE_PWD")
        self.use_gss = os.getenv("RP_REMOTE_GSS_SSH", "False").lower() == "true"
        if self.use_gss:
            if self.remote_pwd or _remote_user:
                warnings.warn(
                    "Both `RP_REMOTE_GSS_SSH` and one of `RP_REMOTE_PWD` or `RP_REMOTE_USER` is set. "
                    "Those options are mutually exclusive, you configuration may be incorrect. "
                    "RP_REMOTE_GSS_SSH will take priority."
                )
            self.remote_user = None
        else:
            self.remote_user = _remote_user if _remote_user else getpass.getuser()

    @property
    def has_process(self) -> bool:
        return self.local_proc is not None or (self.ip is not None and self.pid > 0)

    async def pre_launch(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Launches the specified process within a YARN cluster environment.
        """
        self.kernel_log = None
        kwargs = await super().pre_launch(**kwargs)
        return kwargs

    async def launch_kernel(self, cmd: tyList[str], **kwargs: Any) -> KernelConnectionInfo:
        """
        Launches a kernel process on a selected host.

        NOTE: This overrides the superclass `launch_kernel` method entirely.
        """
        env_dict = kwargs.get("env", {})
        self.assigned_host = self._determine_next_host(env_dict)
        self.ip = gethostbyname(self.assigned_host)  # convert to ip if host is provided
        self.assigned_ip = self.ip

        launch_kwargs = RemoteProvisionerBase._scrub_kwargs(kwargs)
        try:
            result_pid = self._launch_remote_process(cmd, **launch_kwargs)
            self.pid = int(result_pid)
        except Exception as e:
            error_message = f"Failure occurred starting kernel on '{self.ip}'.  Returned result: {e}"
            self.log_and_raise(RuntimeError(error_message))

        self.log_kernel_launch(cmd)

        await self.confirm_remote_startup()

        return self.connection_info

    async def poll(self) -> Optional[int]:
        """Checks if kernel process is still running.

        If this corresponds to a local (popen) process, poll() is called on the subprocess.
        Otherwise, the zero signal is used to determine if active.
        """
        if self.local_proc:  # Use the subprocess if we have one
            return self.local_proc.poll()

        return await self.send_signal(0)  # else use the communication port

    async def send_signal(self, signum: int) -> None:
        """
        Sends `signum` via the communication port.
        The kernel launcher listening on its communication port will receive the signum and perform
        the necessary signal operation local to the process.
        """
        signal_delivered = await self._send_signal_via_listener(signum)
        if not signal_delivered:
            # Fallback
            # if we have a local process, use its method, else determine if the ip is local or remote and issue
            # the appropriate version to signal the process.
            if self.local_proc:
                if self.pgid > 0 and hasattr(os, "killpg"):
                    try:
                        os.killpg(self.pgid, signum)
                        return
                    except OSError:
                        pass
                self.local_proc.send_signal(signum)
            else:
                if self.ip and self.pid > 0:
                    if RemoteProvisionerBase.ip_is_local(self.ip):
                        self.local_signal(signum)
                    else:
                        self.remote_signal(signum)
        return

    async def kill(self, restart=False) -> None:
        """
        Terminate the distributed provisioner process.

        First attempts graceful termination, then forced termination.
        Note that this should only be necessary if the message-based kernel termination has
        proven unsuccessful.
        """
        # If we have a local process, use its method, else signal soft kill first before hard kill.
        res = await self.poll()
        if res is not None:  # Already terminated
            self.log.debug("Distributed: kill: already terminated.")
            return None
        await self.terminate()  # Send -15 signal first
        i = 1
        while await self.poll() is None and i <= max_poll_attempts:
            await asyncio.sleep(poll_interval)
            i = i + 1
        if i > max_poll_attempts:  # Send -9 signal if process is still alive
            if self.local_proc:
                self.local_proc.kill()
                self.log.debug("DistributedProvisioner.kill() called.")
            else:
                if self.ip and self.pid > 0:
                    await self.send_signal(signal.SIGKILL)
                    self.log.debug(f"SIGKILL signal sent to pid: {self.pid}")
        return None

    async def terminate(self, restart=False) -> None:
        """
        Gracefully terminate the distributed provisioner process.

        Note that this should only be necessary if the message-based kernel termination has
        proven unsuccessful.
        """
        # If we have a local process, use its method, else send signal SIGTERM to soft kill.
        if self.local_proc:
            self.local_proc.terminate()
            self.log.debug("DistributedProvisioner.terminate() called.")
        else:
            if self.ip and self.pid > 0:
                await self.send_signal(signal.SIGTERM)
                self.log.debug(f"SIGTERM signal sent to pid: {self.pid}")
        return None

    def _unregister_assigned_host(self) -> None:
        if self.least_connection:
            DistributedProvisioner.kernel_on_host.delete_kernel_id(self.kernel_id)

    async def cleanup(self, restart=False) -> None:
        self._unregister_assigned_host()
        if self.local_stdout:
            self.local_stdout.close()
            self.local_stdout = None
        await super().cleanup()

    def log_kernel_launch(self, cmd: tyList[str]) -> None:
        self.log.info(f"{self.__class__.__name__}: kernel launched.  Host: '{self.assigned_host}', "
                      f"pid: {self.pid}, Kernel ID: {self.kernel_id}, "
                      f"Log file: {self.assigned_host}:{self.kernel_log}, cmd: '{cmd}'.")

    def _launch_remote_process(self, cmd: tyList[str], **kwargs: Any):
        """
            Launch the kernel as indicated by the argv stanza in the kernelspec.  Note that this method
            will bypass use of ssh if the remote host is also the local machine.
        """

        cmd = self._build_startup_command(cmd, **kwargs)
        self.log.debug("Invoking cmd: '{}' on host: {}".format(cmd, self.assigned_host))
        result_pid = 'bad_pid'  # purposely initialize to bad int value

        if RemoteProvisionerBase.ip_is_local(self.ip):
            # launch the local command with redirection in place
            self.local_stdout = open(self.kernel_log, mode='a')
            self.local_proc = launch_kernel(cmd,
                                            stdout=self.local_stdout,
                                            stderr=subprocess.STDOUT,
                                            **kwargs)
            result_pid = str(self.local_proc.pid)
        else:
            # launch remote command via ssh
            result = self.rsh(self.ip, ''.join(cmd))
            for line in result:
                result_pid = line.strip()

        return result_pid

    def _build_startup_command(self, cmd: tyList[str], **kwargs: Any) -> tyList[str]:
        """
        Builds the command to invoke by concatenating envs from kernelspec followed by the kernel argvs.

        We also force nohup, redirection to a file and place in background, then follow with an echo
        for the background pid.

        Note: We optimize for the local case and just return the existing command.
        """

        # Optimized case needs to also redirect the kernel output, so unconditionally compose kernel_log
        env_dict = kwargs['env']
        kid = env_dict.get('KERNEL_ID')
        self.kernel_log = os.path.join(kernel_log_dir, f"kernel-{kid}.log")

        if RemoteProvisionerBase.ip_is_local(self.ip):  # We're local so just use what we're given
            startup_cmd = cmd
        else:  # Add additional envs, including those in kernelspec
            startup_cmd = ''
            if kid:
                startup_cmd += f'export KERNEL_ID="{kid}";'

            kernel_user = env_dict.get('KERNEL_USERNAME')
            if kernel_user:
                startup_cmd += f'export KERNEL_USERNAME="{kernel_user}";'

            impersonation = env_dict.get('RP_IMPERSONATION_ENABLED')
            if impersonation:
                startup_cmd += f'export RP_IMPERSONATION_ENABLED="{impersonation}";'

            for key, value in self.kernel_spec.env.items():
                startup_cmd += "export {}={};".format(key, json.dumps(value).replace("'", "''"))

            startup_cmd += "nohup"
            for arg in cmd:
                startup_cmd += f" {arg}"

            startup_cmd += f" >> {self.kernel_log} 2>&1 & echo $!"  # return the process id

        return startup_cmd

    def _determine_next_host(self, env_dict: Dict) -> str:
        """Simple round-robin index into list of hosts."""
        remote_host = env_dict.get("KERNEL_REMOTE_HOST")
        if self.least_connection:
            next_host = DistributedProvisioner.kernel_on_host.min_or_remote_host(remote_host)
            DistributedProvisioner.kernel_on_host.add_kernel_id(next_host, self.kernel_id)
        else:
            next_host = (
                remote_host
                if remote_host
                else self.remote_hosts[DistributedProvisioner.host_index % self.remote_hosts.__len__()]
            )
            DistributedProvisioner.host_index += 1

        return next_host

    async def confirm_remote_startup(self):
        self.start_time = RemoteProvisionerBase.get_current_time()
        i = 0
        ready_to_connect = False  # we're ready to connect when we have a connection file to use
        while not ready_to_connect:
            i += 1
            await self.handle_timeout()

            self.log.debug("{}: Waiting to connect.  Host: '{}', KernelID: '{}'".
                           format(i, self.assigned_host, self.kernel_id))

            if self.assigned_host != '':
                ready_to_connect = await self.receive_connection_info()

    async def handle_timeout(self):
        """Checks to see if the kernel launch timeout has been exceeded while awaiting connection info."""
        await asyncio.sleep(poll_interval)
        time_interval = RemoteProvisionerBase.get_time_diff(self.start_time)

        if time_interval > self.launch_timeout:
            reason = "Waited too long ({}s) to get connection file.  Check Enterprise Gateway log and kernel " \
                     "log ({}:{}) for more information.". \
                format(self.launch_timeout, self.assigned_host, self.kernel_log)
            timeout_message = "KernelID: '{}' launch timeout due to: {}".format(self.kernel_id, reason)
            await asyncio.get_event_loop().run_in_executor(None, self.kill)
            self.log_and_raise(TimeoutError(timeout_message))

    def _get_ssh_client(self, host) -> paramiko.SSHClient:
        """
        Create a SSH Client based on host, username and password if provided.
        If there is any AuthenticationException/SSHException, raise HTTP Error 403 as permission denied.

        :param host:
        :return: ssh client instance
        """
        ssh = None

        try:
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            host_ip = gethostbyname(host)
            if self.use_gss:
                self.log.debug("Connecting to remote host via GSS.")
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(host_ip, port=ssh_port, gss_auth=True)
            else:
                ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
                if self.remote_pwd:
                    self.log.debug("Connecting to remote host with username and password.")
                    ssh.connect(
                        host_ip,
                        port=ssh_port,
                        username=self.remote_user,
                        password=self.remote_pwd,
                    )
                else:
                    self.log.debug("Connecting to remote host with ssh key.")
                    ssh.connect(host_ip, port=ssh_port, username=self.remote_user)
        except Exception as e:
            http_status_code = 500
            current_host = gethostbyname(gethostname())
            error_message = (
                f"Exception '{type(e).__name__}' occurred when creating a SSHClient at {current_host} connecting "
                f"to '{host}:{ssh_port}' with user '{self.remote_user}', message='{e}'."
            )
            if e is paramiko.SSHException or paramiko.AuthenticationException:
                http_status_code = 403
                error_message_prefix = "Failed to authenticate SSHClient with password"
                error_message = error_message_prefix + (
                    " provided" if self.remote_pwd else "-less SSH"
                )
                error_message = error_message + f"and RP_REMOTE_GSS_SSH={self.use_gss}"

            self.log_and_raise(RuntimeError(error_message))

        return ssh

    def rsh(self, host, command):
        """
        Executes a command on a remote host using ssh.

        Parameters
        ----------
        host : str
            The host on which the command is executed.
        command : str
            The command to execute.

        Returns
        -------
        lines : List
            The command's output.  If stdout is zero length, the stderr output is returned.
        """
        ssh = self._get_ssh_client(host)
        try:
            stdin, stdout, stderr = ssh.exec_command(command, timeout=30)
            lines = stdout.readlines()
            if len(lines) == 0:  # if nothing in stdout, return stderr
                lines = stderr.readlines()
        except Exception as e:
            # Let caller decide if exception should be logged
            raise e

        finally:
            if ssh:
                ssh.close()

        return lines

    def remote_signal(self, signum):
        """
        Sends signal `signum` to process proxy on remote host.
        """
        val = None
        # if we have a process group, use that, else use the pid...
        target = '-' + str(self.pgid) if self.pgid > 0 and signum > 0 else str(self.pid)
        cmd = 'kill -{} {}; echo $?'.format(signum, target)
        if signum > 0:  # only log if meaningful signal (not for poll)
            self.log.debug("Sending signal: {} to target: {} on host: {}".format(signum, target, self.ip))

        try:
            result = self.rsh(self.ip, cmd)
        except Exception as e:
            self.log.warning("Remote signal({}) to '{}' on host '{}' failed with exception '{}'.".
                             format(signum, target, self.ip, e))
            return False

        for line in result:
            val = line.strip()
        if val == '0':
            return None

        return False

    def local_signal(self, signum):
        """
        Sends signal `signum` to local process.
        """
        # if we have a process group, use that, else use the pid...
        target = '-' + str(self.pgid) if self.pgid > 0 and signum > 0 else str(self.pid)
        if signum > 0:  # only log if meaningful signal (not for poll)
            self.log.debug("Sending signal: {} to target: {}".format(signum, target))

        cmd = ['kill', '-' + str(signum), target]

        with open(os.devnull, 'w') as devnull:
            result = subprocess.call(cmd, stderr=devnull)

        if result == 0:
            return None
        return False
