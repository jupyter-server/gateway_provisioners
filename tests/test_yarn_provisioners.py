# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

import os
from uuid import uuid4

import pytest
from jupyter_client import KernelConnectionInfo
from validators import TEST_USER, YarnValidator

YARN_SEED_ENV = {
    "KERNEL_USERNAME": TEST_USER,
    "GP_YARN_ENDPOINT": "my-yarn-cluster.acme.com:7777",
    "GP_ALT_YARN_ENDPOINT": "my-yarn-cluster.acme.com:8888",
}


@pytest.mark.parametrize("seed_env", [YARN_SEED_ENV])
async def test_lifecycle(init_api_mocks, response_manager, get_provisioner, seed_env):

    name = "yarn"
    kernel_id = str(uuid4())
    validator = YarnValidator.create_instance(
        name, seed_env, kernel_id=kernel_id, response_manager=response_manager
    )
    os.environ.update(seed_env)

    provisioner = get_provisioner(name, kernel_id)
    validator.validate_provisioner(provisioner)

    kwargs = {"env": seed_env}
    kwargs = await provisioner.pre_launch(**kwargs)
    validator.validate_pre_launch(kwargs)

    cmd = kwargs.pop("cmd")
    connection_info: KernelConnectionInfo = await provisioner.launch_kernel(cmd, **kwargs)
    validator.validate_launch_kernel(connection_info)

    await provisioner.post_launch(**kwargs)
    validator.validate_post_launch(kwargs)

    assert provisioner.has_process is True, "has_process property has unexpected value: False"

    poll_result = await provisioner.poll()
    assert poll_result is None, f"poll() returned unexpected result: '{poll_result}'"

    # send_signal() would only test remote provisioner and probably better-suited for launcher tests

    # In the yarn provisioner, kill only differs from terminate by sending a kill signal, which
    # we can't really test, so only testing terminate.

    await provisioner.terminate(restart=False)

    # shutdown_requested() would only test remote provisioner and probably better-suited for launcher tests

    await provisioner.cleanup(restart=False)
    assert provisioner.has_process is False, "has_process property has unexpected value: True"
