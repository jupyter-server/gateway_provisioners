import shutil
import tempfile

from os import path
from distutils import dir_util

kernel_launchers_dir = path.join(path.dirname(__file__), 'kernel-launchers')
kernel_resources_dir = path.join(path.dirname(__file__), 'kernel-resources')

launcher_dirs = ['python', 'r', 'scala']
resource_dirs = ['python', 'r', 'scala', 'tensorflow']


def create_staging_directory(parent_dir=None):
    """Creates a temporary staging directory at the specified location.
       If no `parent_dir` is specified, the platform-specific "temp" directory is used.
    """
    return tempfile.mkdtemp(prefix="staging_", dir=parent_dir)


def delete_staging_directory(dir_name):
    """Deletes the specified staging directory."""
    shutil.rmtree(dir_name)


def copy_kernelspec_files(dir_name, launcher_type=None, resource_type=None):
    """Copies the launcher files specified by `launcher_type` to the specified directory."""

    if launcher_type is None and resource_type is None:
        raise ValueError("Invalid parameters.  At least one of 'launcher_type' or 'resource_type' must be specified!")

    if launcher_type is not None and launcher_type not in launcher_dirs:
        raise ValueError("Invalid launcher_type '{}' detected! Must be one of: {}".format(launcher_type, launcher_dirs))

    # If resource is not specified, default to launcher_type.  For the most part it will be the language,
    # but if not, this will raise.
    if resource_type is None:
        resource_type = launcher_type
    if resource_type not in resource_dirs:
        raise ValueError("Invalid resource_type '{}' detected! Must be one of: {}".format(resource_type, resource_dirs))

    if launcher_type is not None:
        src_dir = path.join(kernel_launchers_dir, launcher_type)
        dir_util.copy_tree(src=src_dir, dst=dir_name)

    if resource_type is not None:
        src_dir = path.join(kernel_resources_dir, resource_type)
        dir_util.copy_tree(src=src_dir, dst=dir_name)
