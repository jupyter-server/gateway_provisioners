# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
ARG DOCKER_ORG=elyra
ARG SERVER_APP=${SERVER_APP:-jkg}
ARG BASE_CONTAINER=${DOCKER_ORG}spark-base:${TAG:-dev}

FROM ${BASE_CONTAINER} AS server-base

USER root

# Install appropriate applications
FROM server-base as server-lab
# Do nothing

FROM server-base as server-jkg
RUN pip install jupyter-kernelgateway
# FIXME - Update to JKG start script
CMD /usr/local/bin/bootstrap-kernel.sh

# Select previous image based on KERNEL_LANG ARG value and continue
FROM server-${SERVER_APP} as server-image
ARG SERVER_APP
LABEL SERVER_APP=${SERVER_APP}

# Build images from appropriate source - release or local
FROM server-image AS package-release
# Install remote provisioners from PYPI
# TODO - uncomment once we have a release
#RUN pip install remote_provisioners

# LOCAL (dev) build
FROM server-image AS package-local
# Install remote provisioners from local wheel
COPY remote_provisioners*.whl /tmp/
RUN pip install /tmp/remote_provisioners*.whl && \
	rm -f /tmp/remote_provisioners*.whl

FROM package-${PACKAGE_SOURCE} AS bootstrapped-image
# Select previous image based on PACKAGE_SOURCE ARG value and continue
ARG PACKAGE_SOURCE
LABEL PACKAGE_SOURCE=${PACKAGE_SOURCE}


# Install kernelspecs
RUN jupyter image-bootstrap install --languages ${KERNEL_LANG}

RUN chown jovyan:users /usr/local/bin/bootstrap-kernel.sh && \
	chmod 0755 /usr/local/bin/bootstrap-kernel.sh && \
	chown -R jovyan:users /usr/local/bin/kernel-launchers


USER jovyan
