# Ubuntu 18.04.1 LTS Bionic
ARG SPARK_VERSION=${SPARK_VERSION:-3.2.1}
ARG BASE_CONTAINER=jovyan-base:${TAG:-dev}

FROM ${BASE_CONTAINER} AS spark-base

ENV PATH=$PATH:$CONDA_DIR/bin

USER root

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
    sed -i 's/tini -s/tini -g/g' /opt/entrypoint.sh

#     && \
#    ln -sfn /opt/conda/bin/tini /usr/bin/tini

WORKDIR $SPARK_HOME/work-dir
# Ensure that work-dir is writable by everyone
RUN chmod 0777 $SPARK_HOME/work-dir

ENTRYPOINT [ "/opt/entrypoint.sh" ]

USER jovyan
