# Development Workflow

Here are instructions for setting up a development environment for the
[Gateway Provisioners](https://github.com/jupyter-server/gateway_provisioners)
project. It also includes common steps in the developer workflow such as building Gateway Provisioners,
running tests, building docs, etc.

## Prerequisites

There are a couple of globally-scoped commands that are necessary to build Gateway Provisioners: `make` and `sbt`.

### `make`

Our build framework is based on `make` so please ensure that [GNU make](https://www.gnu.org/software/make/) is
installed on your system.

```{admonition} Important!
:class: warning
If you use the typical `python -m build --wheel` or `hatch run build` commands, the Scala Launcher build (see next item)
will not occur!  Always use `make dist` to build the distribution.
```

### `sbt`

Our Scala launcher is built using `sbt`
([Scala Build Tool](https://www.scala-sbt.org/index.html)).  Please check
[here](https://www.scala-sbt.org/1.x/docs/Setup.html) for installation instructions for your platform.

## Clone the repo

Clone this repository into a local directory.

```bash
# make a directory under your HOME directory to put the source code
mkdir -p ~/projects
cd ~/projects

# clone this repo
git clone https://github.com/jupyter-server/gateway_provisioners.git
```

## Make

Gateway Provisioner's build environment is centered around `make` and the
corresponding [`Makefile`](https://github.com/jupyter-server/gateway_provisioners/blob/main/Makefile).

Entering `make` with no parameters yields the following:

```text
clean-images         Remove all docker images.  Targets clean-base-images, clean-kernel-images, and clean-app-images can also be used.
clean                Remove all build, test, coverage, and Python artifacts
dist                 Build wheel and source distributions
docs                 Generate Sphinx HTML documentation, including API docs
helm-chart           Make helm chart distribution
images               Build all docker images.  Targets base-images, kernel-images, and app-images can also be used.
install              Install the built package to the active Python's site-packages
lint-fix             Run lint with updates enabled
lint                 Check style and linting
push-images          Push all docker images.  Targets push-base-images, push-kernel-images, push-app-images can also be used.
release              Package and upload a release using twine
test                 Run tests with the currently active Python version
```

A typical sequence of commands might include the following:

- Clean the current build environment

  ```text
  make clean
  ```

- Apply changes and ensure updates pass lint

  ```text
  make lint
  ```

- If lint-related errors are present, they can usually be fixed using `lint-fix`

  ```text
  make lint-fix
  ```

- Build the distribution

  ```text
  make dist
  ```

- Run tests via Makefile (`pytest -v`)

  ```text
  make test
  ```

- Build the docs

  ```text
  make docs
  ```

- Build the images

  ```text
  make images
  ```

```{seealso}
See [Kernel-image Dockerfiles](../operators/installing-kernels-container.md#kernel-image-dockerfiles) in our
Operators Guide for additional information regarding image Dockerfiles, build arguments, etc.
```
