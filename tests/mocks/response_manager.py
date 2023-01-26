# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

response_manager_registration = {}


def generate_connection_info(id: str) -> dict:
    comm_port = hash(id) % 65535
    return {
        "comm_port": comm_port,
        "shell_port": comm_port + 1,
        "iopub_port": comm_port + 2,
        "stdin_port": comm_port + 3,
        "control_port": comm_port + 4,
        "hb_port": comm_port + 5,
        "ip": "127.0.0.1",
        "key": id.replace("-", ""),
        "transport": "tcp",
        "signature_scheme": "hmac-sha256",
        "kernel_name": "python3",
    }


# This avoids the response manager from listening for requests and
# an annoying prompt in debug mode.
def mock_socket_listen(self, backlog: int) -> None:
    pass


def mock_register_event(self, kernel_id: str) -> None:
    assert kernel_id not in response_manager_registration
    response_manager_registration[kernel_id] = {}


async def mock_get_connection_info(self, kernel_id: str) -> dict:
    assert kernel_id in response_manager_registration
    return generate_connection_info(kernel_id)
