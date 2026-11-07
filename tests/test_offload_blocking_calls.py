# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Tests that blocking provisioner calls run off the event loop, one at a time per provisioner."""

import asyncio
import contextlib
import threading
import time
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


async def test_container_kill_skipped_without_container(docker_provisioner, monkeypatch):
    probe = LoopProbe()
    monkeypatch.setattr(docker_provisioner, "terminate_container_resources", probe)
    docker_provisioner.container_name = None
    await docker_provisioner.kill()
    probe.assert_loop_responsive(expected_calls=0)


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

    Capacity never frees up here, so the wait ends in a timeout.
    """
    poll_interval = 0.2
    monkeypatch.setattr("gateway_provisioners.yarn.poll_interval", poll_interval)
    yarn_provisioner.yarn_resource_check_wait_time = 2.5 * poll_interval
    availability = LoopProbe(False)
    resource_mgr = fake_resource_manager(
        cluster_scheduler_queue=LoopProbe({"queueName": "default"}),
        cluster_queue_partition=LoopProbe({"partitionName": "gpu"}),
        cluster_scheduler_queue_availability=availability,
    )
    install_resource_manager(lambda **kwargs: resource_mgr)

    async with max_loop_stall() as stall:
        with pytest.raises(TimeoutError, match="Yarn Compute Resource is unavailable"):
            await yarn_provisioner.pre_launch(env=dict(QUEUE_ENV))

    resource_mgr.cluster_scheduler_queue.assert_loop_responsive()
    resource_mgr.cluster_queue_partition.assert_loop_responsive()
    availability.assert_loop_responsive(expected_calls=None)
    assert len(availability.loop_responsive) > 1, "availability should be checked repeatedly"
    assert stall[0] < poll_interval / 2, f"event loop stalled for {stall[0]:.3f}s"


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
