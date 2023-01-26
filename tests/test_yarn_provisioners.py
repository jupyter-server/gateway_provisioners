# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from uuid import uuid4

import pytest
from jupyter_client import KernelConnectionInfo
from utils import TEST_USER, YarnValidator


@pytest.mark.parametrize("seed_env", [{"KERNEL_USERNAME": TEST_USER}])
async def test_lifecycle(init_api_mocks, response_manager, get_provisioner, seed_env):

    name = "yarn"
    kernel_id = str(uuid4())
    validator = YarnValidator.create_instance(
        name, seed_env, kernel_id=kernel_id, response_manager=response_manager
    )

    provisioner = get_provisioner(name, kernel_id)
    validator.validate_provisioner(provisioner)

    kwargs = {"env": seed_env}
    kwargs = await provisioner.pre_launch(**kwargs)
    validator.validate_pre_launch(kwargs)

    cmd = kwargs.pop("cmd")
    connection_info: KernelConnectionInfo = await provisioner.launch_kernel(cmd, **kwargs)
    validator.validate_launch_kernel(connection_info)

    # post-launch()

    # has_kernel()

    # poll()

    # send_signal()? only tests remote provisioner, need to mock connection port
    #  mock _send_signal_via_listener()

    # kill()

    # terminate()

    # shutdown_requested()

    # cleanup()
