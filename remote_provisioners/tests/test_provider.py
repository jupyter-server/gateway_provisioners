import asyncio
import json
import os
import pytest
import re

from jupyter_kernel_mgmt.discovery import KernelFinder

from os.path import join as pjoin
from jupyter_core import paths
from uuid import UUID
from ..provider import RemoteKernelProviderBase
from ..manager import RemoteKernelManager
from ..lifecycle_manager import RemoteKernelLifecycleManager


sample_kernel_json = {'argv': ['cat', '{kernel_id}', '{response_address}'], 'display_name': 'Test kernel', }

foo_kernel_json = {'argv': ['cat', '{kernel_id}', '{response_address}'], 'display_name': 'Test foo kernel', }

bar_kernel_json = {'argv': ['cat', '{kernel_id}', '{response_address}'], 'display_name': 'Test bar kernel', }

foo_connection_info = {'stdin_port': 47557, 'ip': '172.16.18.82', 'control_port': 55288,
                       'hb_port': 55562, 'signature_scheme': 'hmac-sha256',
                       'key': 'e75863c2-4a8a-49b0-b6d2-9e23837d5bd1', 'comm_port': 36458,
                       'kernel_name': '', 'shell_port': 58031, 'transport': 'tcp', 'iopub_port': 52229}


def install_sample_kernel(kernels_dir,
                          kernel_name='sample',
                          kernel_file='kernel.json',
                          json_content=sample_kernel_json):

    """install a sample kernel in a kernels directory"""
    sample_kernel_dir = pjoin(kernels_dir, kernel_name)
    os.makedirs(sample_kernel_dir, exist_ok=True)
    json_file = pjoin(sample_kernel_dir, kernel_file)
    with open(json_file, 'w') as f:
        json.dump(json_content, f)


def is_uuid(uuid_to_test):
    try:
        UUID(uuid_to_test, version=4)
    except ValueError:
        return False
    return True


def is_response_address(addr_to_test):
    return re.match(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}:[0-9]{4,5}$", addr_to_test) is not None


class FooKernelLifecycleManager(RemoteKernelLifecycleManager):
    """A fake kernel provider for testing KernelFinder"""
    connection_info = None

    async def launch_process(self, kernel_cmd, **kwargs):
        assert is_uuid(kernel_cmd[1])
        assert is_response_address(kernel_cmd[2])
        await self.confirm_remote_startup()
        return self

    async def confirm_remote_startup(self):
        self.connection_info = foo_connection_info
        return True

    def shutdown_listener(self):
        pass

    async def kill(self):
        pass


class BarKernelLifecycleManager(FooKernelLifecycleManager):
    pass  # Full inheritance from FooKernelLifecycleManager


class BazKernelLifecycleManager(FooKernelLifecycleManager):
    pass  # Full inheritance from FooKernelLifecycleManager


class FooKernelProvider(RemoteKernelProviderBase):
    """A fake kernelspec provider subclass for testing"""
    id = 'foo'
    kernel_file = 'foo_kspec.json'
    lifecycle_manager_classes = ['remote_kernel_provider.tests.test_provider.FooKernelLifecycleManager']

    @asyncio.coroutine
    def find_kernels(self):
        return super(FooKernelProvider, self).find_kernels()


class BarKernelProvider(RemoteKernelProviderBase):
    """A fake kernelspec provider subclass for testing"""
    id = 'bar'
    kernel_file = 'bar_kspec.json'
    lifecycle_manager_classes = ['remote_kernel_provider.tests.test_provider.BarKernelLifecycleManager']


class BazKernelProvider(RemoteKernelProviderBase):
    """A fake kernelspec provider subclass for testing"""
    id = 'baz'
    kernel_file = 'baz_kspec.json'
    lifecycle_manager_classes = ['remote_kernel_provider.tests.test_provider.BazKernelLifecycleManager']

    @asyncio.coroutine
    def find_kernels(self):
        return {}


@pytest.fixture
def setup_test(setup_env):

    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'))
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'),
                          'foo_kspec', 'foo_kspec.json', foo_kernel_json)
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'),
                          'foo_kspec2', 'foo_kspec.json', foo_kernel_json)

    # This kspec overlaps with foo/foo_kspec.  Will be located as bar/foo_kspec
    install_sample_kernel(pjoin(paths.jupyter_data_dir(), 'kernels'),
                          'foo_kspec', 'bar_kspec.json', bar_kernel_json)


@pytest.fixture
def kernel_finder(setup_test):
    kernel_finder = KernelFinder(providers=[FooKernelProvider(), BarKernelProvider(), BazKernelProvider()])
    return kernel_finder


pytestmark = pytest.mark.asyncio


async def test_find_remote_kernel_provider(kernel_finder):
    fake_kspecs = list(kernel_finder.find_kernels())
    assert len(fake_kspecs) == 3

    foo_kspecs = bar_kspecs = 0
    for name, spec in fake_kspecs:
        assert name.startswith('/foo_kspec', 3)
        assert spec['argv'] == foo_kernel_json['argv']
        if name.startswith('foo/'):
            foo_kspecs += 1
            assert spec['display_name'] == foo_kernel_json['display_name']
        elif name.startswith('bar/'):
            bar_kspecs += 1
            assert spec['display_name'] == bar_kernel_json['display_name']
        elif name.startswith('baz/'):
            assert False  # If we have any, that's wrong.
    assert foo_kspecs == 2
    assert bar_kspecs == 1


async def test_launch_remote_kernel_provider(kernel_finder):
    conn_info, manager = await kernel_finder.launch('foo/foo_kspec')
    assert isinstance(manager, RemoteKernelManager)
    assert conn_info == foo_connection_info
    assert manager.kernel_id is not None
    assert is_uuid(manager.kernel_id)

    await manager.kill()
    assert manager.lifecycle_manager is not None
    assert isinstance(manager.lifecycle_manager, FooKernelLifecycleManager)
    await manager.cleanup()
    assert manager.lifecycle_manager is None
