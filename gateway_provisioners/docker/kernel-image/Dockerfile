# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG KERNEL_LANG=python
ARG PACKAGE_SOURCE=release
ARG BASE_CONTAINER=jupyter/docker-stacks-foundation:2022-11-15

FROM ${BASE_CONTAINER} AS kernel-base

ENV PATH=$PATH:$CONDA_DIR/bin

USER root

# Install appropriate kernels

# Python Kernel (ipykernel)
FROM kernel-base as kernel-python
ENV KERNEL_LANGUAGE=Python
RUN mamba install --quiet --yes \
    'altair' \
    'beautifulsoup4' \
    'bokeh' \
    'bottleneck' \
    'cloudpickle' \
    'conda-forge::blas=*=openblas' \
    'cython' \
    'dask' \
    'dill' \
    'h5py' \
    'ipykernel'\
    'ipympl'\
    'ipywidgets' \
    'matplotlib-base' \
    'numba' \
    'numexpr' \
    'openpyxl' \
    'pandas' \
    'patsy' \
    'protobuf' \
    'pytables' \
    'scikit-image' \
    'scikit-learn' \
    'scipy' \
    'seaborn' \
    'sqlalchemy' \
    'statsmodels' \
    'sympy' \
    'widgetsnbextension'\
    'xlrd' && \
    mamba clean --all -f -y && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

# Scala Kernel (Apache Toree)
FROM kernel-base as kernel-scala
# Scala and JVM should be installed with Spark
ENV KERNEL_LANGUAGE=Scala
RUN pip install apache_toree

# R Kernel (IRKernel)
FROM kernel-base as kernel-r
ENV KERNEL_LANGUAGE=R
# R pre-requisites
RUN apt-get update --yes && \
    apt-get install --yes --no-install-recommends \
    fonts-dejavu \
    unixodbc \
    unixodbc-dev \
    r-cran-rodbc \
    gfortran \
    gcc && \
    apt-get clean && rm -rf /var/lib/apt/lists/*


# R packages including IRKernel which gets installed globally.
# r-e1071: dependency of the caret R package
RUN mamba install --quiet --yes \
    'r-argparse' \
    'r-base' \
    'r-caret' \
    'r-crayon' \
    'r-devtools' \
    'r-e1071' \
    'r-forecast' \
    'r-hexbin' \
    'r-htmltools' \
    'r-htmlwidgets' \
    'r-irkernel' \
    'r-nycflights13' \
    'r-randomforest' \
    'r-rcurl' \
    'r-rmarkdown' \
    'r-rodbc' \
    'r-rsqlite' \
    'r-shiny' \
    'r-tidyverse' \
    'unixodbc' && \
    mamba clean --all -f -y && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

# `r-tidymodels` is not easy to install under arm
RUN set -x && \
    arch=$(uname -m) && \
    if [ "${arch}" == "x86_64" ]; then \
        mamba install --quiet --yes \
            'r-tidymodels' && \
            mamba clean --all -f -y && \
            fix-permissions "${CONDA_DIR}" && \
            fix-permissions "/home/${NB_USER}"; \
    fi;


# Select previous image based on KERNEL_LANG ARG value and continue
FROM kernel-${KERNEL_LANG} as kernel-image
ARG KERNEL_LANG
LABEL KERNEL_LANG=${KERNEL_LANG}

# Build images from appropriate source - release or local
FROM kernel-image AS package-release
# Install remote provisioners from PYPI
RUN pip install gateway_provisioners

# LOCAL (dev) build
FROM kernel-image AS package-local
# Install remote provisioners from local wheel
COPY gateway_provisioners*.whl /tmp/
RUN pip install /tmp/gateway_provisioners*.whl && \
	rm -f /tmp/gateway_provisioners*.whl

FROM package-${PACKAGE_SOURCE} AS bootstrapped-image
# Select previous image based on PACKAGE_SOURCE ARG value and continue
ARG PACKAGE_SOURCE
ARG KERNEL_LANG
LABEL PACKAGE_SOURCE=${PACKAGE_SOURCE}

CMD /usr/local/bin/bootstrap-kernel.sh

# Install bootstrap and applicable launchers (per languages)
RUN jupyter image-bootstrap install --languages ${KERNEL_LANG}

RUN chown jovyan:users /usr/local/bin/bootstrap-kernel.sh && \
	chmod 0755 /usr/local/bin/bootstrap-kernel.sh && \
	chown -R jovyan:users /usr/local/bin/kernel-launchers

USER ${NB_UID}
