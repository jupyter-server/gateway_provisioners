# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Tests for the ResponseManager's processing of connections on a real (loopback) socket."""

import asyncio
import base64
import contextlib
import gc
import json
import logging
import warnings
from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from Cryptodome.Cipher import AES, PKCS1_v1_5
from Cryptodome.PublicKey import RSA
from Cryptodome.Random import get_random_bytes
from Cryptodome.Util.Padding import pad
from mocks.response_manager import generate_connection_info

import gateway_provisioners.response_manager as rm_module
from gateway_provisioners.response_manager import ResponseManager

# How long a valid payload may take to be delivered.  This is well below the default read
# timeout, so delivery cannot depend on a misbehaving connection being dropped first.
DELIVERY_TIMEOUT = 2.0


@pytest.fixture
def live_response_manager(monkeypatch, jp_asyncio_loop):
    """A ResponseManager listening on the loopback interface, with no socket calls mocked."""
    monkeypatch.setattr(rm_module, "response_ip", "127.0.0.1")
    rm = ResponseManager.instance()
    yield rm
    in_flight = set(rm._connection_tasks)
    rm.stop_response_manager()
    # Let the cancelled connection tasks close their sockets before the loop is closed.
    if in_flight:
        jp_asyncio_loop.run_until_complete(asyncio.gather(*in_flight, return_exceptions=True))
    ResponseManager.clear_instance()


def build_payload(public_key: str, connection_info: dict) -> bytes:
    """Builds a version 1 payload the way the kernel launcher's ServerListener._encrypt does."""
    aes_key = get_random_bytes(16)
    connection_info_bytes = json.dumps(connection_info).encode()
    encrypted_connection_info = AES.new(aes_key, AES.MODE_ECB).encrypt(
        pad(connection_info_bytes, 16)
    )
    server_key = RSA.import_key(base64.b64decode(public_key))
    encrypted_key = PKCS1_v1_5.new(server_key).encrypt(aes_key)
    envelope = {
        "version": 1,
        "key": base64.b64encode(encrypted_key).decode(),
        "conn_info": base64.b64encode(encrypted_connection_info).decode(),
    }
    return base64.b64encode(json.dumps(envelope).encode())


async def connect(rm: ResponseManager) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    host, port = rm.response_address.rsplit(":", 1)
    return await asyncio.open_connection(host, int(port))


async def close(writer: asyncio.StreamWriter) -> None:
    """Closes the client connection, which the server may already have dropped."""
    writer.close()
    with contextlib.suppress(ConnectionError):
        await writer.wait_closed()


async def send_payload(rm: ResponseManager, payload: bytes) -> None:
    """Sends a complete payload, then closes the connection - as the kernel launcher does."""
    _, writer = await connect(rm)
    writer.write(payload)
    await writer.drain()
    await close(writer)


async def wait_for_connection_info(rm: ResponseManager, kernel_id: str) -> dict:
    """Polls get_connection_info() like RemoteProvisionerBase.receive_connection_info does."""
    deadline = asyncio.get_running_loop().time() + DELIVERY_TIMEOUT
    while True:
        try:
            return await rm.get_connection_info(kernel_id)
        except TimeoutError:
            if asyncio.get_running_loop().time() >= deadline:
                raise


def kernel_connection_info(kernel_id: str) -> dict:
    return {**generate_connection_info(kernel_id), "kernel_id": kernel_id}


def expected_connection_info(connection_info: dict) -> dict:
    """The ResponseManager converts the connection's key to bytes."""
    return {**connection_info, "key": connection_info["key"].encode()}


def client_peer(writer: asyncio.StreamWriter) -> str:
    """How the server identifies this client in its log messages."""
    host, port = writer.get_extra_info("sockname")[:2]
    return f"{host}:{port}"


def warning_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


async def stall(writer: asyncio.StreamWriter) -> None:
    """Sends nothing and keeps the connection open, like a hung launcher or a port scanner."""


async def flood(writer: asyncio.StreamWriter) -> None:
    """Sends more than the payload size limit and keeps the connection open."""
    writer.write(b"A" * (ResponseManager.MAX_PAYLOAD_SIZE + 1))
    await writer.drain()


Misbehavior = Callable[[asyncio.StreamWriter], Awaitable[None]]


async def test_valid_payload_is_delivered(live_response_manager, caplog):
    rm = live_response_manager
    caplog.set_level(logging.DEBUG, logger=rm.log.name)
    kernel_id = str(uuid4())
    rm.register_event(kernel_id)
    connection_info = kernel_connection_info(kernel_id)
    payload = build_payload(rm.public_key, connection_info)

    await send_payload(rm, payload)

    assert await wait_for_connection_info(rm, kernel_id) == expected_connection_info(
        connection_info
    )
    # Neither the (encrypted) payload nor the connection's key may be logged.
    assert not any(payload.decode() in record.getMessage() for record in caplog.records)
    assert not any(connection_info["key"] in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("misbehave", [stall, flood], ids=["stalled", "oversized"])
async def test_misbehaving_connection_does_not_delay_others(
    live_response_manager, misbehave: Misbehavior
):
    rm = live_response_manager
    kernel_id = str(uuid4())
    rm.register_event(kernel_id)
    connection_info = kernel_connection_info(kernel_id)

    # Connections are accepted in arrival order, so the misbehaving one is accepted first.
    _, writer = await connect(rm)
    try:
        await misbehave(writer)
        await send_payload(rm, build_payload(rm.public_key, connection_info))
        received = await wait_for_connection_info(rm, kernel_id)
    finally:
        await close(writer)

    assert received == expected_connection_info(connection_info)


@pytest.mark.parametrize(
    "misbehave,read_timeout,reason",
    [
        (stall, 0.2, "Timed out"),
        # The long read timeout shows the connection is dropped because of its size.
        (flood, 30.0, "exceeded"),
    ],
    ids=["stalled", "oversized"],
)
async def test_misbehaving_connection_is_closed(
    live_response_manager,
    monkeypatch,
    caplog,
    misbehave: Misbehavior,
    read_timeout: float,
    reason: str,
):
    rm = live_response_manager
    monkeypatch.setattr(rm_module, "response_read_timeout", read_timeout)
    caplog.set_level(logging.WARNING, logger=rm.log.name)

    reader, writer = await connect(rm)
    peer = client_peer(writer)
    try:
        await misbehave(writer)
        # The server closing its end of the connection is observed as end-of-file.
        assert await asyncio.wait_for(reader.read(), DELIVERY_TIMEOUT) == b""
    finally:
        await close(writer)

    warned = warning_messages(caplog)
    assert any(reason in message and peer in message for message in warned), warned


async def test_connection_is_closed_when_its_handler_never_runs(live_response_manager):
    rm = live_response_manager
    # Accept the connection by hand, so that its task is created and then cancelled by
    # stop_response_manager() without the event loop running in between - that is, before
    # the task's handler starts.
    rm._connection_processor.stop()
    reader, writer = await connect(rm)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await rm._process_connections()
            assert len(rm._connection_tasks) == 1
            rm.stop_response_manager()
            # The server closing its end of the connection is observed as end-of-file.
            assert await asyncio.wait_for(reader.read(), DELIVERY_TIMEOUT) == b""
            gc.collect()  # Finalize the server's socket now should it have been left open.
    finally:
        await close(writer)

    # Garbage collection closing the socket, rather than the server, warns of the leak.
    leaks = [str(w.message) for w in caught if issubclass(w.category, ResourceWarning)]
    assert not leaks, leaks


async def test_connections_beyond_the_limit_are_closed_until_capacity_frees(
    live_response_manager, monkeypatch, caplog
):
    rm = live_response_manager
    max_connections = 2
    monkeypatch.setattr(rm_module, "response_max_connections", max_connections)
    # Stalled connections are held for the duration of the test, unless their client drops them.
    monkeypatch.setattr(rm_module, "response_read_timeout", 30.0)
    caplog.set_level(logging.WARNING, logger=rm.log.name)
    kernel_id = str(uuid4())
    rm.register_event(kernel_id)
    connection_info = kernel_connection_info(kernel_id)

    stalled = [await connect(rm) for _ in range(max_connections)]
    try:
        # Connections are accepted in arrival order, so this one is accepted at capacity and
        # closed right away, while the server still holds the stalled connections.
        reader, writer = await connect(rm)
        peer = client_peer(writer)
        try:
            assert await asyncio.wait_for(reader.read(), DELIVERY_TIMEOUT) == b""
        finally:
            await close(writer)
        assert len(rm._connection_tasks) == max_connections
        warned = warning_messages(caplog)
        assert any(
            "GP_RESPONSE_MAX_CONNECTIONS" in message and peer in message for message in warned
        ), warned

        # Capacity frees up once a stalled connection is dropped.  Its client half-closes the
        # connection, then observes the server closing its end once processing has ended.
        dropped_reader, dropped_writer = stalled[0]
        dropped_writer.write_eof()
        assert await asyncio.wait_for(dropped_reader.read(), DELIVERY_TIMEOUT) == b""
        await send_payload(rm, build_payload(rm.public_key, connection_info))
        received = await wait_for_connection_info(rm, kernel_id)
    finally:
        for _, stalled_writer in stalled:
            await close(stalled_writer)

    assert received == expected_connection_info(connection_info)


async def test_connection_rejections_do_not_flood_the_log(
    live_response_manager, monkeypatch, caplog
):
    rm = live_response_manager
    monkeypatch.setattr(rm_module, "response_max_connections", 1)
    monkeypatch.setattr(rm_module, "response_read_timeout", 30.0)
    caplog.set_level(logging.DEBUG, logger=rm.log.name)

    rejected_peers: list[str] = []
    _, stalled_writer = await connect(rm)
    try:
        for _ in range(3):
            reader, writer = await connect(rm)
            rejected_peers.append(client_peer(writer))
            try:
                assert await asyncio.wait_for(reader.read(), DELIVERY_TIMEOUT) == b""
            finally:
                await close(writer)
    finally:
        await close(stalled_writer)

    # Every rejection is logged, but only the first as a warning.
    warned = warning_messages(caplog)
    warned_peers = [peer for peer in rejected_peers if any(peer in m for m in warned)]
    assert warned_peers == rejected_peers[:1], warned
    messages = [r.getMessage() for r in caplog.records]
    assert all(any(peer in m for m in messages) for peer in rejected_peers), messages
