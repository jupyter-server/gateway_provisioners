# Development Workflow

Here are instructions for setting up a development environment for the [Gateway Provisioners]https://github.com/gateway-experiments/gateway_provisioners)
project. It also includes common steps in the developer workflow such as building Gateway Provisioners,
running tests, building docs, packaging kernel specifications, etc.

## Prerequisites

Install [GNU make](https://www.gnu.org/software/make/) on your system.

## Clone the repo

Clone this repository into a local directory.

```bash
# make a directory under your HOME directory to put the source code
mkdir -p ~/projects
cd !$

# clone this repo
git clone https://github.com/gateway-experiments/gateway_provisioners.git
```

## Make

Gateway Provisioner's build environment is centered around `make` and the
corresponding [`Makefile`](https://github.com/gateway-experiments/gateway_provisioners/blob/main/Makefile).

Entering `make` with no parameters yields the following:

```
build-dependencies             install packages necessary to complete the build
clean-build                    remove build artifacts
clean-images                   Remove all docker images.  Targets clean-base-images and clean-kernel-images can also be used.
clean-pyc                      remove Python file artifacts
clean-test                     remove test and coverage artifacts
clean                          remove all build, test, coverage and Python artifacts
dist                           builds wheel and source packages
docs                           generate Sphinx HTML documentation, including API docs
images                         Build all docker images.  Targets base-images and kernel-images can also be used.
install                        install the package to the active Python's site-packages
lint                           check style with flake8
push-images                    Push all docker images.  Targets push-base-images and push-kernel-images can also be used.
release                        package and upload a release
test                           run tests quickly with the default Python
```
