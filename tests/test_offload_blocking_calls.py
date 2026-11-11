# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Tests that blocking provisioner calls run off the event loop, one at a time per provisioner."""

import asyncio
import contextlib
import contextvars
import os
import select
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from mocks.k8s_client import MockCoreV1Api
from validators import TEST_USER

import gateway_provisioners
from gateway_provisioners.remote_provisioner import RemoteProvisionerBase

# Note: gateway_provisioners.yarn must not be imported at module level - doing so binds the real
# ResourceManager before the init_api_mocks fixture can replace it (see validators.py).

# How long a probed call waits for the event loop to prove it is still running.
PROBE_TIMEOUT = 1.0


class LoopProbe:
    """Stands in for a blocking call and records whether the event loop kept running during it.

    Each call schedules a callback on the event loop and waits for it to run.  A call made on
    the event loop's own thread starves that callback, so the wait times out; a call offloaded
    to a worker thread sees it run almost immediately.  Results are returned in order, with
    the last one repeated.
    """

    def __init__(self, *results):
        self.loop = asyncio.get_running_loop()
        self.results = list(results) or [None]
        self.loop_responsive: list[bool] = []

    def __call__(self, *args, **kwargs):
        loop_ran = threading.Event()
        self.loop.call_soon_threadsafe(loop_ran.set)
        self.loop_responsive.append(loop_ran.wait(PROBE_TIMEOUT))
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]

    def assert_loop_responsive(self, expected_calls: int | None = 1) -> None:
        """Asserts the loop ran during every call; `expected_calls=None` accepts any number > 0."""
        if expected_calls is None:
            assert self.loop_responsive, "the probed call was never made"
        else:
            assert len(self.loop_responsive) == expected_calls, "unexpected number of calls"
        assert all(self.loop_responsive), "the event loop was blocked during the call"


class ConcurrencyTracker:
    """Builds blocking stand-ins that record how many of them run at the same time."""

    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.events: list[tuple[str, str]] = []

    def blocking(self, name: str, result=None, duration: float = 0.05):
        def _call(*args, **kwargs):
            with self._lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                self.events.append((name, "start"))
            time.sleep(duration)
            with self._lock:
                self.active -= 1
                self.events.append((name, "end"))
            return result

        return _call


@contextlib.asynccontextmanager
async def max_loop_stall():
    """Measures the longest interval during which the event loop could not run a task."""
    stalls = [0.0]
    stop = asyncio.Event()

    async def _ticker():
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.005)
            now = time.monotonic()
            stalls[0] = max(stalls[0], now - last)
            last = now

    ticker = asyncio.create_task(_ticker())
    await asyncio.sleep(0)  # let the ticker start before the code under test runs
    try:
        yield stalls
    finally:
        stop.set()
        await ticker


class YarnResponse:
    """Minimal stand-in for a yarn-api-client response."""

    def __init__(self, data: dict):
        self.data = data


@pytest.fixture
def no_poll_delay(init_api_mocks, monkeypatch):
    """Shortens the launch-confirmation and YARN polling intervals to keep the tests fast."""
    monkeypatch.setattr(gateway_provisioners.remote_provisioner, "poll_interval", 0.01)
    # Importing gateway_provisioners.yarn here is safe since init_api_mocks is active.
    monkeypatch.setattr("gateway_provisioners.yarn.poll_interval", 0.01)


@pytest.fixture
def docker_provisioner(init_api_mocks, response_manager, get_provisioner):
    provisioner = get_provisioner("docker", str(uuid4()))
    provisioner.container_name = f"{TEST_USER}-{provisioner.kernel_id}"
    return provisioner


@pytest.fixture
def yarn_provisioner(init_api_mocks, response_manager, get_provisioner):
    provisioner = get_provisioner("yarn", str(uuid4()))
    provisioner.application_id = "application_1_0001"
    provisioner.start_time = RemoteProvisionerBase.get_current_time()
    return provisioner


@pytest.mark.parametrize(
    "extension_point,invoke",
    [
        ("get_container_status", lambda p: p.poll()),
        ("terminate_container_resources", lambda p: p.kill()),
        ("terminate_container_resources", lambda p: p.terminate()),
        ("terminate_container_resources", lambda p: p.shutdown_listener(restart=False)),
    ],
    ids=["poll", "kill", "terminate", "shutdown_listener"],
)
async def test_container_calls_do_not_block_loop(
    docker_provisioner, monkeypatch, extension_point, invoke
):
    probe = LoopProbe()
    monkeypatch.setattr(docker_provisioner, extension_point, probe)
    await invoke(docker_provisioner)
    probe.assert_loop_responsive()


async def test_container_startup_does_not_block_loop(
    docker_provisioner, monkeypatch, no_poll_delay
):
    probe = LoopProbe("exited")  # an error state, so startup fails after one status check
    monkeypatch.setattr(docker_provisioner, "get_container_status", probe)
    with pytest.raises(RuntimeError, match="Error starting kernel container"):
        await docker_provisioner.confirm_remote_startup()
    probe.assert_loop_responsive()


@pytest.mark.parametrize(
    "invoke",
    [
        lambda p: p.kill(),
        lambda p: p.terminate(),
        lambda p: p.shutdown_listener(restart=False),
    ],
    ids=["kill", "terminate", "shutdown_listener"],
)
async def test_container_termination_skipped_without_container(
    docker_provisioner, monkeypatch, invoke
):
    """Without a container there is nothing to terminate, so no worker thread is scheduled."""
    probe = LoopProbe()
    monkeypatch.setattr(docker_provisioner, "_terminate_container", probe)
    docker_provisioner.container_name = None
    await invoke(docker_provisioner)
    probe.assert_loop_responsive(expected_calls=0)


async def test_container_kill_during_status_check_terminates_found_container(
    docker_provisioner, monkeypatch
):
    """kill() must not skip termination while a status check that may find the container runs.

    The status check names the container only when it returns, so a kill() deciding there is
    nothing to terminate before then would leave the container running.
    """
    container_name = docker_provisioner.container_name
    docker_provisioner.container_name = None
    status = BlockingCall(result="running")

    def find_container(iteration):
        result = status(iteration)
        docker_provisioner.container_name = container_name
        return result

    terminated = []
    monkeypatch.setattr(docker_provisioner, "get_container_status", find_container)
    monkeypatch.setattr(
        docker_provisioner,
        "terminate_container_resources",
        lambda restart=False: terminated.append(container_name),
    )

    poll = asyncio.create_task(docker_provisioner.poll())
    await status.wait_started()
    kill = asyncio.create_task(docker_provisioner.kill())
    await asyncio.sleep(0.05)
    status.release.set()
    await asyncio.gather(poll, kill)

    assert terminated == [container_name]


async def test_wait_on_local_process_does_not_block_loop(docker_provisioner):
    probe = LoopProbe(0)
    docker_provisioner.local_proc = SimpleNamespace(wait=probe)
    assert await docker_provisioner.wait() == 0
    probe.assert_loop_responsive()


async def test_k8s_namespace_creation_does_not_block_loop(
    init_api_mocks, response_manager, get_provisioner, monkeypatch
):
    monkeypatch.setattr(gateway_provisioners.k8s, "shared_namespace", False)
    probe = LoopProbe()
    monkeypatch.setattr(MockCoreV1Api, "create_namespace", probe)
    provisioner = get_provisioner("kubernetes", str(uuid4()))

    kwargs = await provisioner.pre_launch(env={"KERNEL_USERNAME": TEST_USER})

    probe.assert_loop_responsive()
    expected_namespace = f"{TEST_USER}-{provisioner.kernel_id}"
    assert provisioner.kernel_namespace == expected_namespace
    assert kwargs["env"]["KERNEL_NAMESPACE"] == expected_namespace
    assert provisioner.delete_kernel_namespace is True


async def test_yarn_poll_does_not_block_loop(yarn_provisioner):
    probe = LoopProbe(YarnResponse({"state": "RUNNING"}))
    yarn_provisioner.resource_mgr = SimpleNamespace(cluster_application_state=probe)
    assert await yarn_provisioner.poll() is None
    probe.assert_loop_responsive()


@pytest.mark.parametrize("method", ["kill", "terminate"])
async def test_yarn_shutdown_does_not_block_loop(yarn_provisioner, no_poll_delay, method):
    kill_probe = LoopProbe({})
    state_probe = LoopProbe(YarnResponse({"state": "RUNNING"}), YarnResponse({"state": "KILLED"}))
    yarn_provisioner.resource_mgr = SimpleNamespace(
        cluster_application_kill=kill_probe, cluster_application_state=state_probe
    )
    await getattr(yarn_provisioner, method)()
    kill_probe.assert_loop_responsive()
    state_probe.assert_loop_responsive(expected_calls=2)


async def test_yarn_startup_does_not_block_loop(yarn_provisioner, no_poll_delay):
    probe = LoopProbe(YarnResponse({"app": {"state": "FAILED"}}))
    yarn_provisioner.resource_mgr = SimpleNamespace(cluster_application=probe)
    with pytest.raises(RuntimeError, match="unexpectedly found in state 'FAILED'"):
        await yarn_provisioner.confirm_remote_startup()
    probe.assert_loop_responsive()


@pytest.fixture
def install_resource_manager(monkeypatch):
    """Makes YarnProvisioner.pre_launch() use the given factory to create its ResourceManager."""

    def _install(factory):
        monkeypatch.setattr("gateway_provisioners.yarn.ResourceManager", factory)

    return _install


def fake_resource_manager(**rest_calls) -> SimpleNamespace:
    return SimpleNamespace(get_active_endpoint=lambda: "http://rm:8088", **rest_calls)


async def test_yarn_resource_manager_creation_does_not_block_loop(
    yarn_provisioner, install_resource_manager
):
    # yarn-api-client contacts the configured endpoints to find the active Resource Manager.
    probe = LoopProbe(fake_resource_manager())
    install_resource_manager(probe)
    await yarn_provisioner.pre_launch(env={"KERNEL_USERNAME": TEST_USER})
    probe.assert_loop_responsive()
    assert yarn_provisioner.rm_addr == "http://rm:8088"


QUEUE_ENV = {"KERNEL_USERNAME": TEST_USER, "KERNEL_QUEUE": "default", "KERNEL_NODE_LABEL": "gpu"}


async def test_yarn_queue_wait_does_not_block_loop(
    yarn_provisioner, install_resource_manager, monkeypatch
):
    """Waiting for queue capacity sleeps between checks without blocking the event loop.

    Capacity frees up on the third check, well within the wait time however loaded the machine.
    """
    poll_interval = 0.5
    monkeypatch.setattr("gateway_provisioners.yarn.poll_interval", poll_interval)
    yarn_provisioner.yarn_resource_check_wait_time = 60
    availability = LoopProbe(False, False, True)
    resource_mgr = fake_resource_manager(
        cluster_scheduler_queue=LoopProbe({"queueName": "default"}),
        cluster_queue_partition=LoopProbe({"partitionName": "gpu"}),
        cluster_scheduler_queue_availability=availability,
    )
    install_resource_manager(lambda **kwargs: resource_mgr)

    async with max_loop_stall() as stall:
        await yarn_provisioner.pre_launch(env=dict(QUEUE_ENV))

    resource_mgr.cluster_scheduler_queue.assert_loop_responsive()
    resource_mgr.cluster_queue_partition.assert_loop_responsive()
    availability.assert_loop_responsive(expected_calls=3)
    # Sleeping on the event loop between checks would stall it for a whole poll interval.
    assert stall[0] < poll_interval / 2, f"event loop stalled for {stall[0]:.3f}s"


async def test_yarn_queue_wait_times_out(yarn_provisioner, install_resource_manager, monkeypatch):
    monkeypatch.setattr("gateway_provisioners.yarn.poll_interval", 0.01)
    yarn_provisioner.yarn_resource_check_wait_time = 0
    resource_mgr = fake_resource_manager(
        cluster_scheduler_queue=lambda queue_name: {"queueName": queue_name},
        cluster_queue_partition=lambda queue, node_label: {"partitionName": node_label},
        cluster_scheduler_queue_availability=lambda partition, threshold: False,
    )
    install_resource_manager(lambda **kwargs: resource_mgr)

    with pytest.raises(TimeoutError, match="Yarn Compute Resource is unavailable"):
        await yarn_provisioner.pre_launch(env=dict(QUEUE_ENV))


def available_queue(*availability) -> SimpleNamespace:
    """A ResourceManager whose queue partition reports the given availability, check by check."""
    return fake_resource_manager(
        cluster_scheduler_queue=lambda queue_name: {"queueName": queue_name},
        cluster_queue_partition=lambda queue, node_label: {"partitionName": node_label},
        cluster_scheduler_queue_availability=LoopProbe(*availability),
    )


async def test_yarn_queue_wait_keeps_configured_launch_timeout(
    yarn_provisioner, install_resource_manager, monkeypatch
):
    """The queue wait counts against this launch alone: restarts reuse the provisioner."""
    monkeypatch.setattr("gateway_provisioners.yarn.poll_interval", 0.01)
    yarn_provisioner.yarn_resource_check_wait_time = 60
    resource_mgr = available_queue(False, True)
    install_resource_manager(lambda **kwargs: resource_mgr)
    launch_timeout = yarn_provisioner.launch_timeout

    await yarn_provisioner.pre_launch(env=dict(QUEUE_ENV))

    assert yarn_provisioner.launch_timeout == launch_timeout
    assert 0 < yarn_provisioner.queue_wait_time < launch_timeout


async def test_yarn_queue_wait_using_up_launch_timeout_fails_launch(
    yarn_provisioner, install_resource_manager, monkeypatch
):
    """A queue wait as long as the launch timeout leaves no time for startup.

    The launch fails before an application is submitted, rather than going on with no time left.
    """
    yarn_provisioner.launch_timeout = 30
    resource_mgr = available_queue(True)
    install_resource_manager(lambda **kwargs: resource_mgr)
    # The clock reads 30 seconds since the queue check started, whenever it is read.
    monkeypatch.setattr(RemoteProvisionerBase, "get_time_diff", staticmethod(lambda start: 30.0))

    with pytest.raises(TimeoutError, match="left no time of the 30 second launch timeout"):
        await yarn_provisioner.pre_launch(env=dict(QUEUE_ENV))

    resource_mgr.cluster_scheduler_queue_availability.assert_loop_responsive()  # check completed
    assert yarn_provisioner.launch_timeout == 30


@pytest.mark.parametrize(
    "startup_seconds,timed_out", [(4, False), (6, True)], ids=["within", "exceeded"]
)
async def test_yarn_launch_timeout_counts_queue_wait(
    yarn_provisioner, monkeypatch, startup_seconds, timed_out
):
    """After a 25 second queue wait, a 30 second launch timeout leaves 5 seconds for startup."""
    monkeypatch.setattr("gateway_provisioners.yarn.poll_interval", 0.01)
    yarn_provisioner.launch_timeout = 30
    yarn_provisioner.queue_wait_time = 25.0
    yarn_provisioner.start_time = RemoteProvisionerBase.get_current_time() - 1000 * startup_seconds
    monkeypatch.setattr(yarn_provisioner, "_get_application_id", lambda ignore_final_states: None)
    kill = AsyncMock()
    monkeypatch.setattr(yarn_provisioner, "kill", kill)

    with pytest.raises(TimeoutError) if timed_out else contextlib.nullcontext():
        await yarn_provisioner.handle_launch_timeout()

    assert kill.called is timed_out


async def test_yarn_cleanup_wait_does_not_block_loop(yarn_provisioner):
    probe = LoopProbe(0)
    yarn_provisioner.local_proc = SimpleNamespace(pid=42, poll=lambda: None, wait=probe)
    await yarn_provisioner.cleanup(restart=False)
    probe.assert_loop_responsive()
    assert yarn_provisioner.local_proc is None


async def test_distributed_launch_does_not_block_loop(
    response_manager, get_provisioner, monkeypatch
):
    provisioner = get_provisioner("distributed", str(uuid4()))
    probe = LoopProbe("4242")
    monkeypatch.setattr(provisioner, "_launch_remote_process", probe)
    monkeypatch.setattr(provisioner, "confirm_remote_startup", AsyncMock())

    await provisioner.launch_kernel(["python"], env={"KERNEL_ID": provisioner.kernel_id})

    probe.assert_loop_responsive()
    assert provisioner.pid == 4242


async def test_concurrent_poll_and_terminate_do_not_overlap(docker_provisioner, monkeypatch):
    tracker = ConcurrencyTracker()
    monkeypatch.setattr(
        docker_provisioner, "get_container_status", tracker.blocking("status", "running")
    )
    monkeypatch.setattr(
        docker_provisioner, "terminate_container_resources", tracker.blocking("terminate")
    )

    results = await asyncio.gather(
        docker_provisioner.poll(), docker_provisioner.terminate(), docker_provisioner.poll()
    )

    assert results == [None, None, None]
    assert len(tracker.events) == 6, "every call should have run"
    assert tracker.max_active == 1, f"blocking calls overlapped: {tracker.events}"


async def test_cancelled_call_blocks_next_call_until_its_thread_finishes(
    docker_provisioner, monkeypatch
):
    """A timed-out poll() must not let terminate() race the still-running status thread.

    jupyter_client bounds its shutdown polling with asyncio.wait_for(), which cancels a poll()
    that is waiting on a worker thread - but cannot stop the thread itself.
    """
    tracker = ConcurrencyTracker()
    monkeypatch.setattr(
        docker_provisioner,
        "get_container_status",
        tracker.blocking("status", "running", duration=0.3),
    )
    monkeypatch.setattr(
        docker_provisioner, "terminate_container_resources", tracker.blocking("terminate")
    )

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(docker_provisioner.poll(), timeout=0.05)
    await docker_provisioner.terminate()

    assert tracker.events == [
        ("status", "start"),
        ("status", "end"),
        ("terminate", "start"),
        ("terminate", "end"),
    ]


async def test_failed_call_releases_lock(docker_provisioner, monkeypatch):
    def failing_status(iteration):
        msg = "API unavailable"
        raise RuntimeError(msg)

    monkeypatch.setattr(docker_provisioner, "get_container_status", failing_status)
    with pytest.raises(RuntimeError, match="API unavailable"):
        await docker_provisioner.poll()

    monkeypatch.setattr(docker_provisioner, "get_container_status", lambda iteration: "running")
    assert await asyncio.wait_for(docker_provisioner.poll(), timeout=PROBE_TIMEOUT) is None


# The longest the event loop may stall while a cancelled call waits for its worker thread.  A loop
# blocked on the worker would stall until the call gives up waiting for release (5 x
# PROBE_TIMEOUT), so this leaves room for scheduling delays on a loaded machine without letting
# that through.
MAX_STALL = PROBE_TIMEOUT


class BlockingCall:
    """Stands in for a blocking call that runs in its worker thread until released.

    This lets a test cancel the caller while the call is still in progress.
    """

    def __init__(self, result=None, start_timeout: float = PROBE_TIMEOUT):
        self.result = result
        self.start_timeout = start_timeout
        self.started = threading.Event()
        self.release = threading.Event()

    def __call__(self, *args, **kwargs):
        self.started.set()
        assert self.release.wait(5 * PROBE_TIMEOUT), "the blocking call was never released"
        return self.result

    async def wait_started(self) -> None:
        started = await asyncio.to_thread(self.started.wait, self.start_timeout)
        assert started, "call never started"


async def cancel_while_blocked(coro, blocking_call: BlockingCall) -> None:
    """Cancels 'coro' while 'blocking_call' runs, then releases the call.

    Cancellation must wait for the worker thread - without stalling the event loop - so its
    result can be rolled back before the cancellation reaches the caller.
    """
    task = asyncio.create_task(coro)
    await blocking_call.wait_started()
    async with max_loop_stall() as stall:
        task.cancel()
        await asyncio.sleep(0.05)
        assert not task.done(), "cancellation should wait for the worker thread to finish"
        blocking_call.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert stall[0] < MAX_STALL, f"event loop stalled for {stall[0]:.3f}s"


@pytest.fixture
def remote_launch(response_manager, get_provisioner, monkeypatch):
    """A DistributedProvisioner that takes the SSH launch path, recording remote commands."""
    monkeypatch.setattr(RemoteProvisionerBase, "ip_is_local", staticmethod(lambda ip: False))
    provisioner = get_provisioner("distributed", str(uuid4()))
    provisioner.rsh_commands = []

    def record_rsh(host, command):
        provisioner.rsh_commands.append((host, command))
        return []

    monkeypatch.setattr(provisioner, "_rsh", record_rsh)
    monkeypatch.setattr(provisioner, "confirm_remote_startup", AsyncMock())
    return provisioner


def launch_kernel(provisioner):
    return provisioner.launch_kernel(["python"], env={"KERNEL_ID": provisioner.kernel_id})


# The command run over SSH to roll back a cancelled remote launch whose process id is 4242.
KILL_PROCESS_TREE_4242 = (
    "sh -c '"
    "pid=4242; "
    '[ "$pid" -gt 1 ] || exit 0; '
    'pgid=$(ps -o pgid= -p "$pid" | tr -d " "); '
    'my_pgid=$(ps -o pgid= -p $$ | tr -d " "); '
    "kill_group=; "
    'if [ "$pgid" -gt 1 ] 2>/dev/null && [ -n "$my_pgid" ] && [ "$pgid" != "$my_pgid" ]; then '
    'if [ "$pgid" = "$pid" ] || [ -z "$(ps -o pid= -p "$pgid")" ]; then kill_group=1; fi; '
    "fi; "
    'kill_tree() ( [ "$1" -gt 1 ] || exit 0; kill -STOP "$1" 2>/dev/null; '
    'for child in $(pgrep -P "$1"); do kill_tree "$child"; done; kill -9 "$1" 2>/dev/null ); '
    'kill_tree "$pid"; '
    'if [ -n "$kill_group" ]; then kill -9 "-$pgid" 2>/dev/null; fi'
    "'"
)


async def test_cancelled_remote_launch_kills_launched_process(remote_launch, monkeypatch):
    """A launch cancelled while SSH starts the kernel must not orphan the remote process.

    The launcher has not reported its communication port yet, so kill() could not reach it.
    """
    launch = BlockingCall(result="4242")
    monkeypatch.setattr(remote_launch, "_launch_remote_process", launch)

    await cancel_while_blocked(launch_kernel(remote_launch), launch)

    assert remote_launch.rsh_commands == [(remote_launch.ip, KILL_PROCESS_TREE_4242)]


async def test_timed_out_remote_launch_kills_launched_process(remote_launch, monkeypatch):
    launch = BlockingCall(result="4242")
    monkeypatch.setattr(remote_launch, "_launch_remote_process", launch)
    asyncio.get_running_loop().call_later(0.2, launch.release.set)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(launch_kernel(remote_launch), timeout=0.05)

    assert remote_launch.rsh_commands == [(remote_launch.ip, KILL_PROCESS_TREE_4242)]


@pytest.mark.parametrize("result_pid", ["bad_pid", "", "-1", "0", "1"])
async def test_cancelled_remote_launch_without_valid_pid_runs_no_command(
    remote_launch, monkeypatch, caplog, result_pid
):
    """Only a launched process is killed: pids of 1 and below address init or process groups."""
    launch = BlockingCall(result=result_pid)
    monkeypatch.setattr(remote_launch, "_launch_remote_process", launch)

    await cancel_while_blocked(launch_kernel(remote_launch), launch)

    assert remote_launch.rsh_commands == []
    assert f"invalid process id '{result_pid}'" in caplog.text


needs_process_groups = pytest.mark.skipif(
    sys.platform == "win32", reason="requires POSIX process groups"
)
needs_process_tools = pytest.mark.skipif(
    sys.platform == "win32" or not (shutil.which("ps") and shutil.which("pgrep")),
    reason="requires a POSIX shell with ps and pgrep",
)

# Stands in for a kernel launcher (argv: <report fd> <lifeline fd> <mode>).  It starts a child
# and, in "orphan" mode, a process whose parent exits straight away - as the R launcher's
# listener does - so it is reparented away from the launcher.  Every process holds the report
# pipe's write end, to which the launcher writes their pids once all of them are running, and
# waits on the lifeline pipe: each exits once the test closes the lifeline (or after 60s).
LAUNCHER_SCRIPT = """\
import os
import select
import subprocess
import sys

report_fd, lifeline_fd, mode = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
inherited_fds = (report_fd, lifeline_fd)
wait_for_lifeline = "import select, sys; select.select([int(sys.argv[1])], [], [], 60)"


def start_child():
    child = [sys.executable, "-c", wait_for_lifeline, str(lifeline_fd)]
    return subprocess.Popen(child, stdout=subprocess.DEVNULL, pass_fds=inherited_fds).pid


if mode == "detach":  # report the child's pid and exit, leaving the child behind
    print(start_child())
    sys.exit()

pids = [os.getpid(), start_child()]
if mode == "orphan":
    detach = [sys.executable, sys.argv[0], *sys.argv[1:3], "detach"]
    pids.append(int(subprocess.run(detach, stdout=subprocess.PIPE, pass_fds=inherited_fds).stdout))
os.write(report_fd, " ".join(map(str, pids)).encode() + b"\\n")
select.select([lifeline_fd], [], [], 60)
"""


class LaunchedProcessTree:
    """Observes the processes started from LAUNCHER_SCRIPT through the pipes they all hold.

    Reading the report pipe reaches EOF only once every process holding its write end has
    exited - including any reparented away from the launcher - so no process table needs
    polling.  Closing the lifeline pipe makes any process still running exit.
    """

    def __init__(self, script: Path):
        self.script = script
        self.read_fd, self.write_fd = os.pipe()
        self.lifeline_fd, self._lifeline_write_fd = os.pipe()
        self._open_fds = {self.read_fd, self.write_fd, self.lifeline_fd, self._lifeline_write_fd}
        self.pids: list[int] = []
        self.exited = False

    @property
    def pass_fds(self) -> tuple[int, int]:
        """The descriptors whatever starts the launcher must pass on to it."""
        return self.write_fd, self.lifeline_fd

    def argv(self, mode: str) -> list[str]:
        """The launcher command."""
        return [sys.executable, str(self.script), *map(str, self.pass_fds), mode]

    def wait_running(self, timeout: float = 20.0) -> None:
        """Waits for the launcher to report its processes, then closes this process's write end."""
        report = b""
        while not report.endswith(b"\n"):
            chunk = self._read(timeout)
            assert chunk, "the launcher exited before starting its processes"
            report += chunk
        self.pids = [int(pid) for pid in report.split()]
        self._close(self.write_fd)

    def wait_exited(self, timeout: float = 10.0) -> bool:
        """Returns True once every process has exited, or False if any outlives the timeout."""
        self._close(self.write_fd)
        try:
            self.exited = self._read(timeout) == b""
        except TimeoutError:
            return False
        return self.exited

    def close(self) -> None:
        """Makes every process left behind (by a failing test) exit, then closes the pipes."""
        self._close(self._lifeline_write_fd)
        if not self.exited and not self.wait_exited() and self.pids:
            # Still running despite the lifeline, so stopped: kill what the launcher reported.
            for pid in self.pids:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.kill(pid, signal.SIGKILL)
            self.wait_exited()
        for fd in list(self._open_fds):
            self._close(fd)

    def _read(self, timeout: float) -> bytes:
        ready, _, _ = select.select([self.read_fd], [], [], timeout)
        if not ready:
            msg = f"nothing to read from the process tree after {timeout}s"
            raise TimeoutError(msg)
        return os.read(self.read_fd, 1024)

    def _close(self, fd: int) -> None:
        # Close each descriptor once: its number may be reused as soon as it is closed.
        if fd in self._open_fds:
            self._open_fds.remove(fd)
            os.close(fd)


@pytest.fixture
def process_tree(tmp_path):
    script = tmp_path / "launcher.py"
    script.write_text(LAUNCHER_SCRIPT)
    tree = LaunchedProcessTree(script)
    yield tree
    tree.close()


@needs_process_groups
@pytest.mark.parametrize("mode", ["child", "orphan"], ids=["child", "reparented-descendant"])
async def test_cancelled_local_launch_kills_launcher_process_group(
    response_manager, get_provisioner, monkeypatch, tmp_path, process_tree, mode
):
    """A local launch cancelled after the launcher started its listener must not orphan it.

    jupyter_client starts the launcher in a new session, so it leads a process group holding
    every process it starts - even those reparented when their own parent exits.
    """
    monkeypatch.setattr("gateway_provisioners.distributed.kernel_log_dir", str(tmp_path))
    provisioner = get_provisioner("distributed", str(uuid4()))  # localhost: launched locally
    launch_remote_process = provisioner._launch_remote_process
    blocked = BlockingCall(start_timeout=30)

    def launch_then_block(cmd, **kwargs):
        blocked.result = launch_remote_process(cmd, **kwargs)
        process_tree.wait_running()
        return blocked(cmd, **kwargs)

    monkeypatch.setattr(provisioner, "_launch_remote_process", launch_then_block)
    monkeypatch.setattr(provisioner, "confirm_remote_startup", AsyncMock())
    launch = provisioner.launch_kernel(
        process_tree.argv(mode),
        env={"KERNEL_ID": provisioner.kernel_id},
        pass_fds=process_tree.pass_fds,
    )
    try:
        await cancel_while_blocked(launch, blocked)

        assert await asyncio.to_thread(process_tree.wait_exited), "processes outlived the launch"
        assert provisioner.local_proc is None
    finally:
        blocked.release.set()
        if provisioner.local_proc is not None:  # not rolled back: reap the launcher regardless
            provisioner.local_proc.kill()
            provisioner.local_proc.wait(timeout=10)
        if provisioner.local_stdout:
            provisioner.local_stdout.close()


@pytest.fixture
def rsh_on_this_host(remote_launch, monkeypatch):
    """Makes remote_launch run its remote commands on this host, through a shell as sshd does."""
    remote_launch.rsh_results = []

    def run_here(host, command):
        result = subprocess.run(  # noqa: S602 - runs the provisioner's own fixed command
            command, shell=True, capture_output=True, text=True, timeout=30, check=False
        )
        remote_launch.rsh_results.append(result)
        return result.stdout.splitlines(keepends=True)

    monkeypatch.setattr(remote_launch, "_rsh", run_here)
    return remote_launch


@needs_process_tools
def test_rollback_kills_remote_launch_process_group(rsh_on_this_host, process_tree, tmp_path):
    """Rolling back a remote launch kills every process it started, even reparented ones.

    sshd runs the startup command in a shell it makes a process group leader, which starts the
    launcher in the background, echoes its pid and exits - so that group holds the launch's
    processes and nothing else, wherever they were reparented to.
    """
    log = shlex.quote(str(tmp_path / "kernel.log"))
    startup_cmd = f"{shlex.join(process_tree.argv('orphan'))} >> {log} 2>&1 & echo $!"
    with subprocess.Popen(  # noqa: S603 - a fixed command built by the test
        ["/bin/sh", "-c", startup_cmd],
        start_new_session=True,
        stdout=subprocess.PIPE,
        pass_fds=process_tree.pass_fds,
        text=True,
    ) as shell:
        result_pid = shell.communicate(timeout=30)[0].strip()
    process_tree.wait_running()

    rsh_on_this_host._abandon_launched_process(result_pid)

    assert [result.stderr for result in rsh_on_this_host.rsh_results] == [""]
    assert process_tree.wait_exited(), "processes of the cancelled launch survived"


@needs_process_tools
def test_rollback_spares_remote_process_group_it_does_not_own(rsh_on_this_host, process_tree):
    """A launcher sharing a process group led by another live process is killed with its
    descendants, but the rest of the group is left alone."""
    sleeper = [sys.executable, "-c", "import time; time.sleep(60)"]
    leader = subprocess.Popen(sleeper, process_group=0)  # noqa: S603
    launcher = subprocess.Popen(  # noqa: S603
        process_tree.argv("child"), process_group=leader.pid, pass_fds=process_tree.pass_fds
    )
    try:
        process_tree.wait_running()

        rsh_on_this_host._abandon_launched_process(str(launcher.pid))

        assert [result.stderr for result in rsh_on_this_host.rsh_results] == [""]
        assert process_tree.wait_exited(), "the launcher or its child survived"
        assert leader.poll() is None, "another process in the launcher's group was killed"
    finally:
        for process in (launcher, leader):
            process.kill()
            process.wait(timeout=10)


async def test_failed_cancelled_launch_needs_no_rollback(remote_launch, monkeypatch):
    launch = BlockingCall()

    def failing_launch(cmd, **kwargs):
        launch(cmd, **kwargs)
        msg = "ssh: connect to host failed"
        raise OSError(msg)

    monkeypatch.setattr(remote_launch, "_launch_remote_process", failing_launch)

    await cancel_while_blocked(launch_kernel(remote_launch), launch)

    assert remote_launch.rsh_commands == []


async def test_failed_rollback_does_not_mask_cancellation(remote_launch, monkeypatch, caplog):
    launch = BlockingCall(result="4242")
    monkeypatch.setattr(remote_launch, "_launch_remote_process", launch)

    def unreachable_host(host, command):
        msg = "host unreachable"
        raise OSError(msg)

    monkeypatch.setattr(remote_launch, "_rsh", unreachable_host)

    await cancel_while_blocked(launch_kernel(remote_launch), launch)

    assert "host unreachable" in caplog.text


@pytest.mark.parametrize(
    "shared,env,expect_deleted",
    [
        (False, {}, True),
        (True, {}, False),
        (False, {"KERNEL_NAMESPACE": "team-namespace"}, False),
    ],
    ids=["created", "shared", "client-provided"],
)
async def test_cancelled_k8s_pre_launch_deletes_only_created_namespace(
    init_api_mocks, response_manager, get_provisioner, monkeypatch, shared, env, expect_deleted
):
    """A launch cancelled while its namespace is set up must not leave a namespace behind."""
    monkeypatch.setattr(gateway_provisioners.k8s, "shared_namespace", shared)
    deleted = []
    monkeypatch.setattr(
        MockCoreV1Api, "delete_namespace", lambda self, name, body: deleted.append(name)
    )
    provisioner = get_provisioner("kubernetes", str(uuid4()))
    determine_namespace = provisioner._determine_kernel_namespace
    blocked = BlockingCall()

    def determine_namespace_then_block(**kwargs):
        blocked.result = determine_namespace(**kwargs)
        return blocked(**kwargs)

    monkeypatch.setattr(provisioner, "_determine_kernel_namespace", determine_namespace_then_block)

    await cancel_while_blocked(
        provisioner.pre_launch(env={"KERNEL_USERNAME": TEST_USER, **env}), blocked
    )

    assert deleted == ([f"{TEST_USER}-{provisioner.kernel_id}"] if expect_deleted else [])
    assert provisioner.delete_kernel_namespace is False


def cancel_tasks_created_since(tasks_before: set[asyncio.Task]) -> None:
    """Cancels every pending task created since 'tasks_before' was taken.

    This is what event-loop teardown does (e.g., when asyncio.run() returns): it cancels every
    pending task at once - not just the one awaiting a blocking call.
    """
    for task in asyncio.all_tasks() - tasks_before:
        task.cancel()


async def test_loop_teardown_keeps_lock_until_worker_finishes(docker_provisioner, monkeypatch):
    """Teardown releases a blocking call's caller at once, but not the lock its worker holds."""
    tasks_before = asyncio.all_tasks()
    status = BlockingCall(result="running")
    monkeypatch.setattr(docker_provisioner, "get_container_status", status)
    poll = asyncio.create_task(docker_provisioner.poll())
    await status.wait_started()
    lock = docker_provisioner._blocking_call_lock
    try:
        cancel_tasks_created_since(tasks_before)
        await asyncio.wait({poll}, timeout=PROBE_TIMEOUT)
        assert poll.cancelled(), "the cancelled caller should not wait for the worker"
        assert lock.locked(), "the lock was released while the worker still runs"
    finally:
        status.release.set()

    await asyncio.wait_for(lock.acquire(), timeout=PROBE_TIMEOUT)
    lock.release()


async def test_loop_teardown_still_rolls_back_cancelled_launch(remote_launch, monkeypatch):
    """Teardown must not skip the rollback of a launch whose worker is still running.

    asyncio.run() waits for the tasks it cancels, so the launch can still wait for its worker
    and kill the process it started.
    """
    tasks_before = asyncio.all_tasks()
    launch = BlockingCall(result="4242")
    monkeypatch.setattr(remote_launch, "_launch_remote_process", launch)
    task = asyncio.create_task(launch_kernel(remote_launch))
    await launch.wait_started()
    try:
        cancel_tasks_created_since(tasks_before)
        await asyncio.sleep(0.05)
        assert not task.done(), "the cancelled launch should wait for its worker to finish"
        assert remote_launch._blocking_call_lock.locked(), "lock released while the worker runs"
    finally:
        launch.release.set()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert remote_launch.rsh_commands == [(remote_launch.ip, KILL_PROCESS_TREE_4242)]
    assert not remote_launch._blocking_call_lock.locked()


REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")


async def test_blocking_call_runs_in_callers_context(docker_provisioner):
    """Like asyncio.to_thread(), a blocking call sees the caller's context variables."""
    REQUEST_ID.set("request-1")
    assert await docker_provisioner._run_blocking(REQUEST_ID.get) == "request-1"
