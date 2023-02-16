# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG BASE_CONTAINER=jupyter/docker-stacks-foundation:2022-11-15

FROM ${BASE_CONTAINER} AS spark-base

ENV PATH=$PATH:$CONDA_DIR/bin

USER root

# The following installation and configuration of Spark was adopted from
# https://github.com/jupyter/docker-stacks/blob/main/pyspark-notebook/Dockerfile

# Spark dependencies
# Default values can be overridden at build time
# All ARGs following SPARK_VERSION have values that must correspond to
# that version of Spark.  See https://spark.apache.org/downloads.html
# (OPENJDK_VERSION can be any of 8, 11, 17)
ARG SPARK_VERSION=${SPARK_VERSION:-3.3.1}
ARG SPARK_CHECKSUM=${SPARK_CHECKSUM:-817f89d83ffacda1c2075d28d4a649bc007a0dd4b8edeac4b2c5e0365efc34fafceff0afedc809faa0e687c6aabf0ff6dbcda329e9045692d700c63018d93171}
ARG HADOOP_VERSION=${HADOOP_VERSION:-2}
ARG SCALA_VERSION=${SCALA_VERSION:-2.12}
ARG OPENJDK_VERSION=${OPENJDK_VERSION:-17}

# JDK installation
RUN apt-get update --yes && \
    apt-get install --yes --no-install-recommends \
    "openjdk-${OPENJDK_VERSION}-jre-headless" \
    ca-certificates-java && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Spark installation
WORKDIR /tmp

ENV APACHE_SPARK_VERSION="${SPARK_VERSION}" \
    HADOOP_VERSION="${HADOOP_VERSION}" \
    OPENJDK_VERSION="${OPENJDK_VERSION}" \
    SCALA_VERSION="${SCALA_VERSION}" \
    SPARK_HOME="/opt/spark" \
    SPARK_OPTS="--driver-java-options=-Xms1024M --driver-java-options=-Xmx4096M --driver-java-options=-Dlog4j.logLevel=info" \
    PATH="${PATH}:/opt/spark/bin"

RUN if [ "${SCALA_VERSION}" == "2.12" ]; then \
    wget -qO "spark.tgz" "https://archive.apache.org/dist/spark/spark-${APACHE_SPARK_VERSION}/spark-${APACHE_SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz"; \
  else \
    wget -qO "spark.tgz" "https://archive.apache.org/dist/spark/spark-${APACHE_SPARK_VERSION}/spark-${APACHE_SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}-scala${SCALA_VERSION}.tgz"; \
  fi && \
  echo "${SPARK_CHECKSUM} *spark.tgz" | sha512sum -c - && \
  tar xzf "spark.tgz" -C /opt --owner root --group root --no-same-owner && \
  rm "spark.tgz"

# Configure Spark
RUN if [ "${SCALA_VERSION}" == "2.12" ]; then \
    ln -s "spark-${APACHE_SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}" "${SPARK_HOME}"; \
  else \
    ln -s "spark-${APACHE_SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}-scala${SCALA_VERSION}" "${SPARK_HOME}"; \
  fi

# Download entrypoint.sh from matching tag for use in Kubernetes
RUN cd ${SPARK_HOME}/bin && \
    wget https://raw.githubusercontent.com/apache/spark/v${SPARK_VERSION}/resource-managers/kubernetes/docker/src/main/dockerfiles/spark/entrypoint.sh && \
    chmod a+x ${SPARK_HOME}/bin/entrypoint.sh && \
    sed -i 's/tini -s/tini -g/g' ${SPARK_HOME}/bin/entrypoint.sh

WORKDIR ${SPARK_HOME}/work-dir
# Ensure that work-dir is writable by everyone
RUN chmod 0777 ${SPARK_HOME}/work-dir

ENTRYPOINT [ "/opt/spark/bin/entrypoint.sh" ]

USER ${NB_UID}

# Install pyarrow
RUN mamba install --quiet --yes \
    'pyarrow' && \
    mamba clean --all -f -y && \
    fix-permissions "${CONDA_DIR}" && \
    fix-permissions "/home/${NB_USER}"

EXPOSE 4040
