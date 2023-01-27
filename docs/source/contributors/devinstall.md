# Development Workflow

Here are instructions for setting up a development environment for the \[Gateway Provisioners\]https://github.com/gateway-experiments/gateway_provisioners)
project. It also includes common steps in the developer workflow such as building Gateway Provisioners,
running tests, building docs, packaging kernel specifications, etc.

## Prerequisites

### `make`

Our build framework is based on `make` so please ensure that [GNU make](https://www.gnu.org/software/make/) is
installed on your system.  Note: if you use the typical `python -m build --wheel` command, it will bypass
the build of the Scala launcher (see next item).

### `sbt`

Our Scala launcher is built using `sbt`
([Scala Build Tool](https://www.scala-sbt.org/index.html)).  Please check
[here](https://www.scala-sbt.org/1.x/docs/Setup.html) for installation instructions for your platform.
Our `make build-dependencies` target will check that `sbt` is in your path and issue a warning
if it can't find such a file, but continues with the build.

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

```text
build-dependencies             Install packages necessary to complete the build
clean-images                   Remove all docker images.  Targets clean-base-images and clean-kernel-images can also be used.
clean                          Remove all build, test, coverage, and Python artifacts
dist                           Build wheel and source distributions
docs                           Generate Sphinx HTML documentation, including API docs
images                         Build all docker images.  Targets base-images and kernel-images can also be used.
install                        Install the package to the active Python's site-packages
lint                           Check style and linting using pre-commit
push-images                    Push all docker images.  Targets push-base-images and push-kernel-images can also be used.
release                        Package and upload a release using twine
test                           Run tests with the currently active Python version
```

A typical sequence of commands might include the following:

```bash
# clean the environment
make clean

# apply changes and ensure updates pass lint
make lint

# build and install changes
make install

# run tests via Makefile (and manually)
make test

# checkin and push commits as necessary
```
