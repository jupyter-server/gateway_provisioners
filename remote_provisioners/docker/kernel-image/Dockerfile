# Ubuntu 18.04.1 LTS Bionic
ARG SPARK_VERSION=${SPARK_VERSION:-3.2.1}
ARG HAS_SPARK=false
ARG KERNEL_LANG=python
ARG PACKAGE_SOURCE=release
ARG BASE_CONTAINER=base-kernel:dev

FROM ${BASE_CONTAINER} AS base

ENV PATH=$PATH:$CONDA_DIR/bin

USER root

FROM base as spark-true
# Spark Distribution ++++++++++
# This should come before Scala since it (for now) requires Spark.
ARG SPARK_VERSION
ENV SPARK_VER $SPARK_VERSION
LABEL SPARK_VERSION=${SPARK_VERSION}
ENV SPARK_HOME /opt/spark

RUN apt-get update && apt-get install -y \
    openjdk-8-jdk \
    curl
#    libssl-dev

ENV JAVA_HOME /usr/lib/jvm/java-1.8.0-openjdk-amd64

RUN curl -s https://archive.apache.org/dist/spark/spark-${SPARK_VER}/spark-${SPARK_VER}-bin-hadoop2.7.tgz | \
    tar -xz -C /opt && \
    ln -s ${SPARK_HOME}-${SPARK_VER}-bin-hadoop2.7 $SPARK_HOME

# Download entrypoint.sh from matching tag
# Use tini from Anaconda installation
RUN cd /opt/ && \
    wget https://raw.githubusercontent.com/apache/spark/v${SPARK_VER}/resource-managers/kubernetes/docker/src/main/dockerfiles/spark/entrypoint.sh && \
    chmod a+x /opt/entrypoint.sh && \
    sed -i 's/tini -s/tini -g/g' /opt/entrypoint.sh && \
    ln -sfn /opt/conda/bin/tini /usr/bin/tini

WORKDIR $SPARK_HOME/work-dir
# Ensure that work-dir is writable by everyone
RUN chmod 0777 $SPARK_HOME/work-dir

ENTRYPOINT [ "/opt/entrypoint.sh" ]
# End - Spark Distribution ----------

FROM base as spark-false
# Do nothing

FROM spark-${HAS_SPARK} as kernel-base
# Select previous image based on HAS_SPARK ARG value and continue
# by installing the kernel
ARG HAS_SPARK
LABEL HAS_SPARK=${HAS_SPARK}

FROM kernel-base as kernel-python
# Install appropriate kernels
# Python Kernel (ipykernel)  ++++++++++
RUN pip install ipykernel
# End - Python Kernel  ----------

FROM kernel-base as kernel-scala
# Scala Kernel (Apache Toree)  ++++++++++
RUN pip install apache_toree
# Scala and JVM should be installed with Spark
# End - Scala Kernel  ----------

FROM kernel-base as kernel-r
# R Kernel (IRKernel)  ++++++++++
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
# End - R Kernel  ----------

FROM kernel-${KERNEL_LANG} as kernel-image
# Select previous image based on KERNEL_LANG ARG value and continue
ARG KERNEL_LANG
LABEL KERNEL_LANG=${KERNEL_LANG}

# Build images from appropriate source - release or local
FROM kernel-image AS package-release
# Install remote provisioners from PYPI
#RUN pip install remote_provisioners
RUN pip install jupyter_events

# LOCAL branch
FROM kernel-image AS package-local
# Install remote provisioners from local wheel
COPY remote_provisioners*.whl /tmp/
RUN pip install /tmp/remote_provisioners*.whl && \
	rm -f /tmp/remote_provisioners*.whl

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


USER jovyan
