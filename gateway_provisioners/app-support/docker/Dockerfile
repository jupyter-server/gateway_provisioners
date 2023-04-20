# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG DOCKER_ORG=elyra
ARG PACKAGE_SOURCE=release
ARG SERVER_APP=${SERVER_APP:-jkg}
ARG BASE_CONTAINER=${DOCKER_ORG}/gp-spark-base:${TAG:-dev}

FROM ${BASE_CONTAINER} AS server-base

CMD /usr/local/bin/start-application.sh

COPY start-application.sh /usr/local/bin

USER root

# Install appropriate applications
FROM server-base as server-lab
RUN pip install jupyterlab
ENV APP_NAME "Jupyter Lab"
ENV APP_CMD jupyter-lab

FROM server-base as server-jkg
RUN pip install jupyter-kernel-gateway
ENV APP_NAME "Jupyter Kernel Gateway"
ENV APP_CMD jupyter-kernelgateway

# Select previous image based on SERVER_APP ARG value and continue
FROM server-${SERVER_APP} as server-image
ARG SERVER_APP
LABEL SERVER_APP=${SERVER_APP}

# Build images from appropriate source - release or local
FROM server-image AS app-release
# Install remote provisioners from PYPI
RUN pip install "gateway_provisioners[k8s,docker]"

# LOCAL (dev) build
FROM server-image AS app-local
# Install remote provisioners from local wheel
COPY gateway_provisioners*.whl /tmp/
RUN pip install `find /tmp/gateway_provisioners*.whl -print`"[k8s,docker]" && \
	rm -f /tmp/gateway_provisioners*.whl

FROM app-${PACKAGE_SOURCE} AS gp-installed-image
# Select previous image based on PACKAGE_SOURCE ARG value and continue
ARG PACKAGE_SOURCE
LABEL PACKAGE_SOURCE=${PACKAGE_SOURCE}

# Install kernelspecs.  We will install K8s, Docker and DockerSwarm specs, but only set the
# APP_ALLOWED_KERNELS env to the docker-based (including Swarm) images since the helm charts
# will set APP_ALLOWED_KERNELS to the k8s specs.
RUN jupyter k8s-spec install --language Python
RUN jupyter k8s-spec install --language Python --spark
RUN jupyter k8s-spec install --language R
RUN jupyter k8s-spec install --language R --spark
RUN jupyter k8s-spec install --language Scala
RUN jupyter k8s-spec install --language Scala --spark
RUN jupyter k8s-spec install --spark --crd
RUN jupyter docker-spec install --language Python
RUN jupyter docker-spec install --language R
RUN jupyter docker-spec install --language Scala
RUN jupyter docker-spec install --language Python --swarm --kernel-name docker_swarm_python --display-name "Docker Swarm Python"
RUN jupyter docker-spec install --language R --swarm --kernel-name docker_swarm_r --display-name "Docker Swarm R"
RUN jupyter docker-spec install --language Scala --swarm --kernel-name docker_swarm_scala --display-name "Docker Swarm Scala"
# Set the allowed kernels list relative to the docker-based specs.  Note, that we will use a syntax similar
# to what the helm charts produce so that we can share the same logic to manipulate these values into usable options.
ENV APP_ALLOWED_KERNELS "[\"docker_python\",\"docker_r\",\"docker_scala\",\"docker_swarm_python\",\"docker_swarm_r\",\"docker_swarm_scala\"]"

RUN chown jovyan:users /usr/local/bin/start-application.sh && \
	chmod 0755 /usr/local/bin/start-application.sh && \
	chown -R jovyan:users /usr/local/share/jupyter/kernels

EXPOSE 8888

USER ${NB_UID}
