from remote_kernel_provider import spec_utils

from os import path
import glob
import pytest


def test_staging_directory(tmpdir):
    # Create two staging dirs, one in the temp location, the other with no parent.
    staging_dir = spec_utils.create_staging_directory(parent_dir=tmpdir.dirname)
    assert path.isdir(staging_dir)
    assert path.basename(staging_dir).startswith("staging_")

    staging_dir2 = spec_utils.create_staging_directory()
    assert path.isdir(staging_dir2)
    assert path.basename(staging_dir2).startswith("staging_")

    # Ensure the two directories differ
    assert staging_dir != staging_dir2

    # Remove the staging dirs
    spec_utils.delete_staging_directory(staging_dir2)
    assert not path.exists(staging_dir2)

    spec_utils.delete_staging_directory(staging_dir)
    assert not path.exists(staging_dir)
    assert path.isdir(tmpdir.dirname)


def test_invalid_parameters(tmpdir):
    kernel_name = 'invalid'

    staging_dir = spec_utils.create_staging_directory(parent_dir=tmpdir.dirname)
    spec_dir = path.join(staging_dir, kernel_name)

    # use a bogus launch-type...
    with pytest.raises(ValueError) as ve:
        assert spec_utils.copy_kernelspec_files(spec_dir, launcher_type='bogus-type')
    assert str(ve.value).startswith("Invalid launcher_type 'bogus-type'")

    # and a bogus resource-type...
    with pytest.raises(ValueError) as ve:
        assert spec_utils.copy_kernelspec_files(spec_dir, launcher_type='python', resource_type='bogus-type')
    assert str(ve.value).startswith("Invalid resource_type 'bogus-type'")

    # and no launcher or resource types specified...
    with pytest.raises(ValueError) as ve:
        assert spec_utils.copy_kernelspec_files(spec_dir)
    assert str(ve.value).startswith("Invalid parameters.  At least one of 'launcher_type' or 'resource_type' must")

    spec_utils.delete_staging_directory(staging_dir)
    assert not path.exists(staging_dir)


def test_copy_python_launcher(tmpdir):
    kernel_name = 'python_kernel'

    staging_dir = spec_utils.create_staging_directory(parent_dir=tmpdir.dirname)
    spec_dir = path.join(staging_dir, kernel_name)

    spec_utils.copy_kernelspec_files(spec_dir, launcher_type='python')

    assert path.isdir(spec_dir)
    scripts_dir = path.join(spec_dir, 'scripts')
    assert path.isdir(scripts_dir)
    launcher_file = path.join(spec_dir, 'scripts', 'launch_ipykernel.py')
    assert path.isfile(launcher_file)

    spec_utils.delete_staging_directory(staging_dir)
    assert not path.exists(launcher_file)
    assert not path.exists(scripts_dir)
    assert not path.exists(spec_dir)


def test_copy_r_launcher(tmpdir):
    kernel_name = 'r_kernel'

    staging_dir = spec_utils.create_staging_directory(parent_dir=tmpdir.dirname)
    spec_dir = path.join(staging_dir, kernel_name)

    spec_utils.copy_kernelspec_files(spec_dir, launcher_type='r')

    assert path.isdir(spec_dir)
    resource_file = path.join(spec_dir, 'kernel.js')
    assert path.isfile(resource_file)
    resource_file = path.join(spec_dir, 'logo-64x64.png')
    assert path.isfile(resource_file)
    scripts_dir = path.join(spec_dir, 'scripts')
    assert path.isdir(scripts_dir)
    launcher_file = path.join(spec_dir, 'scripts', 'launch_IRkernel.R')
    assert path.isfile(launcher_file)
    gateway_file = path.join(spec_dir, 'scripts', 'gateway_listener.py')
    assert path.isfile(gateway_file)

    spec_utils.delete_staging_directory(staging_dir)
    assert not path.exists(gateway_file)
    assert not path.exists(launcher_file)
    assert not path.exists(scripts_dir)
    assert not path.exists(resource_file)
    assert not path.exists(spec_dir)


def test_copy_scala_launcher(tmpdir):
    kernel_name = 'scala_kernel'

    staging_dir = spec_utils.create_staging_directory(parent_dir=tmpdir.dirname)
    spec_dir = path.join(staging_dir, kernel_name)

    spec_utils.copy_kernelspec_files(spec_dir, launcher_type='scala')

    assert path.isdir(spec_dir)
    lib_dir = path.join(spec_dir, 'lib')
    assert path.isdir(lib_dir)
    launcher_file = path.join(spec_dir, 'lib', 'toree-launcher_*')
    matches = glob.glob(launcher_file)
    assert len(matches) == 1
    launcher_file = matches[0]
    assert path.isfile(launcher_file)

    toree_jar = path.join(spec_dir, 'lib', 'toree-assembly-*')
    matches = glob.glob(toree_jar)
    assert len(matches) == 1
    toree_jar = matches[0]
    assert path.isfile(toree_jar)

    spec_utils.delete_staging_directory(staging_dir)
    assert not path.exists(toree_jar)
    assert not path.exists(launcher_file)
    assert not path.exists(lib_dir)
    assert not path.exists(spec_dir)


def test_copy_only_resource(tmpdir):
    kernel_name = 'resource-only'

    staging_dir = spec_utils.create_staging_directory(parent_dir=tmpdir.dirname)
    spec_dir = path.join(staging_dir, kernel_name)

    spec_utils.copy_kernelspec_files(spec_dir, launcher_type=None, resource_type='r')

    assert path.isdir(spec_dir)
    resource_file = path.join(spec_dir, 'kernel.js')
    assert path.isfile(resource_file)
    resource_file = path.join(spec_dir, 'logo-64x64.png')
    assert path.isfile(resource_file)
    scripts_dir = path.join(spec_dir, 'scripts')
    assert not path.exists(scripts_dir)

    spec_utils.delete_staging_directory(staging_dir)
    assert not path.exists(resource_file)
    assert not path.exists(spec_dir)
