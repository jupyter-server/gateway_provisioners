#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.

from __future__ import print_function

# the name of the project
name = 'remote_provisioners'

import os
import sys

from setuptools import setup
from setuptools.command.bdist_egg import bdist_egg
from setuptools.command.test import test as TestCommand

v = sys.version_info
if v[:2] < (3, 6):
    error = "ERROR: %s requires Python version 3.6 or above." % name
    print(error, file=sys.stderr)
    sys.exit(1)

pjoin = os.path.join
here = os.path.abspath(os.path.dirname(__file__))
pkg_root = pjoin(here, name)

packages = []
for d, _, _ in os.walk(pjoin(here, name)):
    if os.path.exists(pjoin(d, '__init__.py')):
        packages.append(d[len(here) + 1:].replace(os.path.sep, '.'))

version_ns = {}
with open(pjoin(here, name, '_version.py')) as f:
    exec(f.read(), {}, version_ns)


class bdist_egg_disabled(bdist_egg):
    """Disabled version of bdist_egg

    Prevents setup.py install from performing setuptools' default easy_install,
    which it should never ever do.
    """
    def run(self):
        sys.exit("Aborting implicit building of eggs. Use `pip install .` to install from source.")


# From https://pytest.readthedocs.io/en/2.7.3/goodpractises.html
class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # use import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main([self.pytest_args])
        sys.exit(errno)


setup_args = dict(
    name=name,
    version=version_ns['__version__'],
    packages=packages,
    description="Jupyter protocol implementation and client libraries",
    author='Jupyter Development Team',
    author_email='jupyter@googlegroups.com',
    url='https://jupyter.org',
    license='BSD',
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    install_requires=[
        'jupyter_client',
        'paramiko>=2.4.0',
        'pexpect>=4.2.0',
        'pycryptodomex>=3.9.7',
        'tornado>=5.1',
        'traitlets>=4.3.3',
    ],
    extras_require={
        "kerberos": ['requests_kerberos'],
        "yarn": ['requests', 'yarn-api-client'],
        "k8s": ['kubernetes>=4.0.0'],
    },
    tests_require=[
        'mock',
        'pytest'
    ],
    entry_points={
        'jupyter_client.kernel_provisioners': [
            'yarn-provisioner = remote_provisioners.yarn:YarnProvisioner',
        ]
    },
    python_requires=">=3.5",
    cmdclass={
        'bdist_egg': bdist_egg if 'bdist_egg' in sys.argv else bdist_egg_disabled,
        'test': PyTest,
    },
    include_package_data=True,
)


if __name__ == '__main__':
    setup(**setup_args)
