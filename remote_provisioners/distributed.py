# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Code related to managing kernels running in YARN clusters."""

import asyncio
import getpass
import json
import os
import paramiko
import signal
import subprocess

from socket import gethostbyname, gethostname
from traitlets import default, List
from typing import Any, Dict, List as tyList, Optional
from jupyter_client import launch_kernel, KernelConnectionInfo

from .remote_provisioner import RemoteProvisionerBase, p

poll_interval = float(os.getenv('RP_POLL_INTERVAL', '0.5'))
max_poll_attempts = int(os.getenv('RP_MAX_POLL_ATTEMPTS', '10'))
kernel_log_dir = os.getenv("RP_KERNEL_LOG_DIR", '/tmp')  # would prefer /var/log, but its only writable by root

ssh_port = int(os.getenv('RP_SSH_PORT', '22'))

# These envs are not documented and should default to current user and None, respectively.  These
# exist just in case we find them necessary in some configurations (where the service user
# must be different).  However, tests show that that configuration doesn't work - so there
# might be more to do.  At any rate, we'll use these variables for now.
remote_user = None
remote_pwd = None


class DistributedProvisioner(RemoteProvisionerBase):
    """
    Kernel lifecycle management for clusters via ssh.
    """
    host_index = 0

    remote_hosts_env = 'RP_REMOTE_HOSTS'
    remote_hosts_default_value = 'localhost'
    remote_hosts = List(default_value=[remote_hosts_default_value], config=True,
                        help="""Bracketed comma-separated list of hosts on which DistributedProcessProxy
                        kernels will be launched e.g., ['host1','host2']. (RP_REMOTE_HOSTS env var
                        - non-bracketed, just comma-separated)""")

    @default('remote_hosts')
    def remote_hosts_default(self):
        return os.getenv(self.remote_hosts_env, self.remote_hosts_default_value).split(',')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kernel_log = None

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
        self.assigned_host = self._determine_next_host()
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
        result = await self.terminate()  # Send -15 signal first
        i = 1
        while await self.poll() is None and i <= max_poll_attempts:
            await asyncio.sleep(poll_interval)
            i = i + 1
        if i > max_poll_attempts:  # Send -9 signal if process is still alive
            if self.local_proc:
                result = self.local_proc.kill()
                self.log.debug(f"DistributedProvisioner.kill(): {result}")
            else:
                if self.ip and self.pid > 0:
                    await self.send_signal(signal.SIGKILL)
                    self.log.debug(f"SIGKILL signal sent to pid: {self.pid}")
        return result

    async def terminate(self, restart=False) -> None:
        """
        Gracefully terminate the distributed provisioner process.

        Note that this should only be necessary if the message-based kernel termination has
        proven unsuccessful.
        """
        # If we have a local process, use its method, else send signal SIGTERM to soft kill.
        result = None
        if self.local_proc:
            result = self.local_proc.terminate()
            self.log.debug(f"DistributedProvisioner.terminate(): {result}")
        else:
            if self.ip and self.pid > 0:
                await self.send_signal(signal.SIGTERM)
                self.log.debug(f"SIGTERM signal sent to pid: {self.pid}")
        return result

    async def cleanup(self, restart=False) -> None:
        pass

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
            log_fd = open(self.kernel_log, mode='w')
            self.local_proc = launch_kernel(cmd,
                                            stdout=log_fd,
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
        self.kernel_log = os.path.join(kernel_log_dir, "kernel-{}.log".format(kid))

        if RemoteProvisionerBase.ip_is_local(self.ip):  # We're local so just use what we're given
            startup_cmd = cmd
        else:  # Add additional envs, including those in kernelspec
            startup_cmd = ''
            if kid:
                startup_cmd += 'export KERNEL_ID="{}";'.format(kid)

            kuser = env_dict.get('KERNEL_USERNAME')
            if kuser:
                startup_cmd += 'export KERNEL_USERNAME="{}";'.format(kuser)

            impersonation = env_dict.get('RP_IMPERSONATION_ENABLED')
            if impersonation:
                startup_cmd += 'export RP_IMPERSONATION_ENABLED="{}";'.format(impersonation)

            for key, value in self.kernel_spec.env.items():
                startup_cmd += "export {}={};".format(key, json.dumps(value).replace("'", "''"))

            startup_cmd += 'nohup'
            for arg in cmd:
                startup_cmd += ' {}'.format(arg)

            startup_cmd += ' >> {} 2>&1 & echo $!'.format(self.kernel_log)  # return the process id

        return startup_cmd

    def _determine_next_host(self):
        """Simple round-robin index into list of hosts."""
        next_host = self.remote_hosts[DistributedProvisioner.host_index % self.remote_hosts.__len__()]
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

    def _get_ssh_client(self, host):
        """
        Create a SSH Client based on host, username and password if provided.
        If there is any AuthenticationException/SSHException, raise HTTP Error 403 as permission denied.

        :param host:
        :return: ssh client instance
        """
        ssh = None

        global remote_user
        global remote_pwd
        if remote_user is None:
            remote_user = os.getenv('RP_REMOTE_USER', getpass.getuser())
            remote_pwd = os.getenv('RP_REMOTE_PWD')  # this should use password-less ssh

        try:
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
            host_ip = gethostbyname(host)
            if remote_pwd:
                ssh.connect(host_ip, port=ssh_port, username=remote_user, password=remote_pwd)
            else:
                ssh.connect(host_ip, port=ssh_port, username=remote_user)
        except Exception as e:
            current_host = gethostbyname(gethostname())
            error_message = "Exception '{}' occurred when creating a SSHClient at {} connecting " \
                            "to '{}:{}' with user '{}', message='{}'.". \
                format(type(e).__name__, current_host, host, ssh_port, remote_user, e)
            if e is paramiko.SSHException or paramiko.AuthenticationException:
                error_message_prefix = "Failed to authenticate SSHClient with password"
                error_message = error_message_prefix + (" provided" if remote_pwd else "-less SSH")
                self.log_and_raise(PermissionError(error_message))
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
