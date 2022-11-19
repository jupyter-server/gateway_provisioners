Operators Guide
===============

These pages are targeted at *operators* that need to deploy and configure a Jupyter server instance with remote provisioners.

.. admonition:: Use cases

    - *As an operator, I want to fix the bottleneck on the local server due to large number of kernels running on it and the size of each kernel (spark driver) process, by deploying the Remote Provisioners, such that kernels can be launched as managed resources within a Hadoop YARN cluster, distributing the resource-intensive driver processes across the cluster, while still allowing the multiple data analysts to leverage the compute power of a large cluster.*
    - *As an operator, I want to constrain applications to specific port ranges so I can more easily identify issues and manage network configurations that adhere to my corporate policy.*
    - *As an operator, I want to constrain the number of active kernels that each of my users can have at any given time.*


Deploying Remote Provisioners
-----------------------------
The deployment of Enterprise Gateway consists of several items, depending on
the nature of the target environment.  Because this topic differs depending on
whether the runtime environment is targeting containers or traditional servers,
we've separated the discussions accordingly.

Container-based deployments
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Remote Provisioners includes support for two forms of container-based environments, Kubernetes
and Docker.

.. toctree::
   :maxdepth: 1
   :name: container-deployments

   deploy-kubernetes
   deploy-docker

Server-based deployments
~~~~~~~~~~~~~~~~~~~~~~~~
Tasks for traditional server deployments are nearly identical with respect to
Remote Provisioners' installation, differing slightly with how the kernel
specifications are configured.  As a result, we marked those topics
as "common" relative to the others.

FIXME - review the "common" wording above

.. toctree::
   :maxdepth: 1
   :name: node-deployments

   installing-rp
   installing-kernels
   deploy-yarn-cluster
   deploy-distributed

Configuring Remote Provisioners
-------------------------------
The Remote Provisioners package adheres to
`Jupyter's common configuration approach <https://jupyter.readthedocs.io/en/latest/use/config.html>`_
. However, because its a library package and not a standalone application, you must add its configurable
items into the hosting application's configuration file (recommended) or by setting the corresponding
environment variables.

.. toctree::
   :maxdepth: 1
   :name: configuring

   config-file
   config-add-env
   config-env-debug
   config-sys-env
   config-kernel-override
   config-security
