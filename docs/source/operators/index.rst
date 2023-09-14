Operators Guide
===============

These pages are targeted at *operators* that need to deploy and configure a Jupyter server instance with
gateway provisioners.

.. admonition:: Use cases

    - *As an operator, I want to fix the bottleneck on the local server due to large number of kernels running on it and the size of each kernel (spark driver) process, by deploying the Gateway Provisioners, such that kernels can be launched as managed resources within a Hadoop YARN cluster, distributing the resource-intensive driver processes across the cluster, while still allowing the multiple data analysts to leverage the compute power of a large cluster.*
    - *As an operator, I want to constrain applications to specific port ranges so I can more easily identify issues and manage network configurations that adhere to my corporate policy.*


Deploying Gateway Provisioners
------------------------------
When considering the deployment and configuration of Gateway Provisioners it is important
to understand where your users notebooks will be located relative to the compute resources
you wish to leverage.

For example, if your users use notebooks on their local desktops but
want to leverage kernels running within a Kubernetes cluster, the deployment and configuration
of Gateway Provisioners should take place within a Gateway server (docker image) that can be remote from the
user's desktop.

If, on the other hand, your users already run within a Kubernetes cluster via JupyterHub (for example),
then the deployment and configuration of Gateway Provisioners would take place within the Jupyter Lab container
image that is launched on behalf of each user.

Regardless of *which* host application to update, Gateway Provisioners are deployed and configured wherever the
kernel process is ultimately launched. In any case, the host application is using ``jupyter_client`` to launch kernels.

Container-based deployments
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Gateway Provisioners includes support for two forms of container-based environments, Kubernetes
and Docker.

.. toctree::
   :maxdepth: 1
   :name: container-deployments

   installing-gp-container
   installing-kernels-container
   deploy-kubernetes
   deploy-docker

Server-based deployments
~~~~~~~~~~~~~~~~~~~~~~~~
Tasks for traditional server deployments are nearly identical to container-based deployments
except the commands are not entered within a ``Dockerfile``, but rather in the shell of the
server where the host application resides.

.. toctree::
   :maxdepth: 1
   :name: node-deployments

   installing-gp
   installing-kernels
   deploy-yarn-cluster
   deploy-distributed


.. _configuring-gp:

Configuring Gateway Provisioners
--------------------------------
The Gateway Provisioners package adheres to
`Jupyter's common configuration approach <https://jupyter.readthedocs.io/en/latest/use/config.html>`_
. However, because its a library package and not a standalone application, you must add its configurable
items into the hosting application's configuration file (recommended) or by setting the corresponding
environment variables.

.. toctree::
   :maxdepth: 1
   :name: configuration

   config-file
   config-add-env
   config-env-debug
   config-sys-env
   config-kernel-override
   config-security
