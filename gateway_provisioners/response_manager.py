# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Response manager used by remote provisioners."""

import asyncio
import base64
import errno
import json
import os
import random
import re
from asyncio import Event
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket, timeout
from typing import Any

from Cryptodome.Cipher import AES, PKCS1_v1_5
from Cryptodome.PublicKey import RSA
from Cryptodome.Util.Padding import unpad
from jupyter_client import localinterfaces
from tornado.ioloop import PeriodicCallback
from traitlets.config import SingletonConfigurable

from .config_mixin import poll_interval, socket_timeout

response_ip = os.getenv("GP_RESPONSE_IP", None)
desired_response_port = int(os.getenv("GP_RESPONSE_PORT", 8877))
response_port_retries = int(os.getenv("GP_RESPONSE_PORT_RETRIES", 10))
response_addr_any = bool(os.getenv("GP_RESPONSE_ADDR_ANY", "False").lower() == "true")

connection_interval = (
    poll_interval / 100.0
)  # already polling, so make connection timeout a fraction of outer poll


# Allow users to specify local ips (regular expressions can be used) that should not be included
# when determining the response address.  For example, on systems with many network interfaces,
# some may have their IPs appear the local interfaces list (e.g., docker's 172.17.0.* is an example)
# that should not be used.  This env can be used to indicate such IPs.
prohibited_local_ips = os.getenv("GP_PROHIBITED_LOCAL_IPS", "").split(",")


def _get_local_ip() -> str:
    """
    Honor the prohibited IPs, locating the first not in the list.
    """
    for ip in localinterfaces.public_ips():
        is_prohibited = False
        for prohibited_ip in prohibited_local_ips:  # exhaust prohibited list, applying regexs
            if re.match(prohibited_ip, ip):
                is_prohibited = True
                break
        if not is_prohibited:
            return ip
    return localinterfaces.public_ips()[0]  # all were prohibited, so go with the first


local_ip = _get_local_ip()

random.seed()


class Response(Event):
    """Combines the event behavior with the kernel launch response."""

    _response = None

    @property
    def response(self):
        return self._response

    @response.setter
    def response(self, value):
        """Set the response.  NOTE: this marks the event as set."""
        self._response = value
        self.set()


class ResponseManager(SingletonConfigurable):
    """
    Singleton that manages the responses from each kernel launcher at startup.

    This singleton does the following:
    1. Acquires a public and private RSA key pair at first use to encrypt and decrypt the
    received responses.  The public key is sent to the launcher during startup
    and is used by the launcher to encrypt the AES key the launcher uses to encrypt
    the connection information, while the private key remains in the server and is
    used to decrypt the AES key from the response - which it then uses to decrypt
    the connection information.
    2. Creates a single socket based on the configuration settings that is listened on
    via a periodic callback.
    3. On receipt, it decrypts the response (key then connection info) and posts the
    response payload to a map identified by the kernel_id embedded in the response.
    4. Provides a wait mechanism for callers to poll to get their connection info
    based on their registration (of kernel_id).
    """

    KEY_SIZE = 1024  # Can be small since its' only used to {en,de}crypt the AES key.
    _instance = None

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._response_ip = None
        self._response_port = None
        self._response_socket = None
        self._connection_processor = None

        # Create encryption keys...
        self._private_key = RSA.generate(ResponseManager.KEY_SIZE)
        self._public_key = self._private_key.publickey()
        self._public_pem = self._public_key.export_key("PEM")

        # Event facility...
        self._response_registry: dict = {}

        # Start the response manager (create socket, periodic callback, etc.) ...
        self._start_response_manager()

    @property
    def public_key(self) -> str:
        """Provides the string-form of public key PEM with header/footer/newlines stripped."""
        return (
            self._public_pem.decode()
            .replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", "")
            .replace("\n", "")
        )

    @property
    def response_address(self) -> str:
        return f"{self._response_ip}:{self._response_port}"

    def register_event(self, kernel_id: str) -> None:
        """Register kernel_id so its connection information can be processed."""
        self._response_registry[kernel_id] = Response()

    async def get_connection_info(self, kernel_id: str) -> dict:
        """Performs a timeout wait on the event, returning the connection information on completion."""
        await asyncio.wait_for(self._response_registry[kernel_id].wait(), connection_interval)
        return self._response_registry.pop(kernel_id).response

    def _prepare_response_socket(self):
        """Prepares the response socket on which connection info arrives from remote kernel launcher."""
        s = socket(AF_INET, SOCK_STREAM)
        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)

        # If response_addr_any is enabled (default disabled), we will permit the server to listen
        # on all addresses, else we will honor a configured response IP (via env) over the local IP
        # (which is the default).
        # Multiple IP bindings should be configured for containerized configurations (k8s) that need to
        # launch kernels into external YARN clusters.
        bind_ip = local_ip if response_ip is None else response_ip
        bind_ip = bind_ip if response_addr_any is False else ""

        response_port = desired_response_port
        for port in ResponseManager._random_ports(response_port, response_port_retries + 1):
            try:
                s.bind((bind_ip, port))
            except OSError as e:
                if e.errno == errno.EADDRINUSE:
                    self.log.info(f"Response port {port} is already in use, trying another port...")
                    continue
                elif e.errno in (
                    errno.EACCES,
                    getattr(errno, "WSAEACCES", errno.EACCES),
                ):
                    self.log.warning(
                        f"Permission to bind to response port {port} denied - continuing..."
                    )
                    continue
                else:
                    err_msg = f"Failed to bind to port '{port}' for response address due to: '{e}'"
                    raise RuntimeError(err_msg) from e
            else:
                response_port = port
                break
        else:
            msg = f"No available response port could be found after {response_port_retries + 1} attempts"
            self.log.critical(msg)
            raise RuntimeError(msg)

        self.log.info(
            f"ResponseManager is bound to port {response_port} for remote kernel connection information."
        )
        s.listen(128)
        s.settimeout(socket_timeout)
        self._response_socket = s
        self._response_port = response_port
        self._response_ip = local_ip if response_ip is None else response_ip

    def _start_response_manager(self) -> None:
        """If not already started, creates and starts the periodic callback to process connections."""
        if self._response_socket is None:
            self._prepare_response_socket()

        if self._connection_processor is None:
            self._connection_processor = PeriodicCallback(self._process_connections, 0.1, 0.1)
            self._connection_processor.start()

    def stop_response_manager(self) -> None:
        """Stops the connection processor."""
        if self._connection_processor is not None:
            self._connection_processor.stop()
            self._connection_processor = None

        if self._response_socket is not None:
            self._response_socket = None

    async def _process_connections(self) -> None:
        """Checks the socket for data, if found, decrypts the payload and posts to 'wait map'."""
        loop = asyncio.get_event_loop()
        data = ""
        conn = None
        try:
            assert self._response_socket is not None
            conn, addr = await loop.sock_accept(self._response_socket)
            while True:
                buffer = await loop.sock_recv(conn, 1024)
                if not buffer:  # send is complete, process payload
                    self.log.debug(f"Received payload '{data}'")
                    payload = self._decode_payload(data)
                    self.log.debug(f"Decrypted payload '{payload}'")
                    self._post_connection(payload)
                    break
                data = data + buffer.decode(
                    encoding="utf-8"
                )  # append what we received until we get no more...
        except timeout:
            pass
        except Exception as ex:
            self.log.error(f"Failure occurred processing connection: {ex}")
        if conn:
            conn.close()

    def _decode_payload(self, data) -> dict:
        """
        Decodes the payload.

        Decodes the payload, identifying the payload's version and returns a dictionary
        representing the kernel's connection information.

        Version "0" payloads do not specify a kernel-id within the payload, nor do they
        include a 'key', 'version' or 'conn_info' fields.  They are purely an AES encrypted
        form of the base64-encoded JSON connection information, and encrypted using the
        kernel-id as a key.  Since no kernel-id is in the payload, we will capture the keys
        of registered kernel-ids and attempt to decrypt the payload until we find the
        appropriate registrant.

        Version "1+" payloads are a base64-encoded JSON string consisting of a 'version', 'key'
        and 'conn_info' fields.  The 'key' field will be decrpyted using the private key to
        reveal the AES key, which is then used to decrypt the `conn_info` field.

        Once decryption has taken place, the connection information string is loaded into a
        dictionary and returned.
        """

        payload_str = base64.b64decode(data)
        try:
            payload = json.loads(payload_str)
            # Get the version
            version = payload.get("version")
            if version is None:
                err_msg = "Payload received from kernel does not include a version indicator!"
                raise ValueError(err_msg)
            self.log.debug(f"Version {version} payload received.")

            if version == 1:
                # Decrypt the AES key using the RSA private key
                encrypted_aes_key = base64.b64decode(payload["key"].encode())
                cipher = PKCS1_v1_5.new(self._private_key)
                aes_key = cipher.decrypt(encrypted_aes_key, b"\x42")
                # Per docs, don't convey that decryption returned sentinel.  So just let
                # things fail "naturally".
                # Decrypt and unpad the connection information using the just-decrypted AES key
                cipher = AES.new(aes_key, AES.MODE_ECB)
                encrypted_connection_info = base64.b64decode(payload["conn_info"].encode())
                connection_info_str = unpad(
                    cipher.decrypt(encrypted_connection_info), 16  # type:ignore[call-arg]
                ).decode()
            else:
                err_msg = f"Unexpected version indicator received: {version}!"
                raise ValueError(err_msg)
        except Exception as ex:
            # Could be version "0", walk the registrant kernel-ids and attempt to decrypt using each as a key.
            # If none are found, re-raise the triggering exception.
            self.log.debug(f"decode_payload exception - {ex.__class__.__name__}: {ex}")
            connection_info_str = None
            for kernel_id in self._response_registry.keys():
                aes_key = kernel_id[0:16]
                try:
                    cipher = AES.new(aes_key.encode("utf-8"), AES.MODE_ECB)
                    decrypted_payload = cipher.decrypt(payload_str)  # type:ignore[call-arg]
                    # Version "0" responses use custom padding, so remove that here.
                    connection_info_str = "".join(
                        [decrypted_payload.decode("utf-8").rsplit("}", 1)[0], "}"]
                    )
                    # Try to load as JSON
                    new_connection_info = json.loads(connection_info_str)
                    # Add kernel_id into dict, then dump back to string so this can be processed as valid response
                    new_connection_info["kernel_id"] = kernel_id
                    connection_info_str = json.dumps(new_connection_info)
                    self.log.warning(
                        f"WARNING!!!! Legacy kernel response received for kernel_id '{kernel_id}'! "
                        "Update kernel launchers to current version!"
                    )
                    break  # If we're here, we made it!
                except Exception as ex2:
                    # Any exception fails this experiment and we continue
                    self.log.debug(
                        f"Received the following exception detecting legacy kernel "
                        f"response - {ex2.__class__.__name__}: {ex2}"
                    )
                    connection_info_str = None

            if connection_info_str is None:
                raise ex

        # and convert to usable dictionary
        assert connection_info_str is not None
        connection_info = json.loads(connection_info_str)
        if "key" in connection_info:  # Convert key to bytes
            connection_info["key"] = connection_info["key"].encode()
        return connection_info

    def _post_connection(self, connection_info: dict) -> None:
        """Posts connection information into "wait map" based on kernel_id value."""
        kernel_id = connection_info.get("kernel_id")
        if kernel_id is None:
            self.log.error("No kernel id found in response!  Kernel launch will fail.")
            return
        if kernel_id not in self._response_registry:
            self.log.error(
                f"Kernel id '{kernel_id}' has not been registered and will not be processed!"
            )
            return

        self.log.debug(f"Connection info received for kernel '{kernel_id}': {connection_info}")
        self._response_registry[kernel_id].response = connection_info

    @staticmethod
    def _random_ports(port: int, n):
        """Generate a list of n random ports near the given port.

        The first 5 ports will be sequential, and the remaining n-5 will be
        randomly selected in the range [port-2*n, port+2*n].
        """
        for i in range(min(5, n)):
            yield port + i
        for _ in range(n - 5):
            yield max(1, port + random.randint(-2 * n, 2 * n))
