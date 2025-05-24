Users Guide
===========

Gateway Provisioners is a package available to any application that leverages ``jupyter_client``
to manage its kernels.  While all kernels launched using Gateway Provisioners run remotely from
their *launching application*, some require that the launching application reside within the cluster
in which the kernels will run, while others do not.  As a result, deployment steps for a given
Gateway provisioner will vary, and are covered in our `Operators Guide <../operators/index.html>`_ .

Examples of applications that leverage ``jupyter_client`` include, but are not limited to, the
following:

 - `JupyterLab <https://jupyterlab.readthedocs.io/en/stable/>`_ - the next-generation web-based
   user interface for Project Jupyter.  Kernels are typically local to the Lab server process, but
   it is straightforward to redirect kernel management to a Gateway server.
 - `Papermill <https://papermill.readthedocs.io/en/latest/>`_ - a tool for parameterizing and
   executing Jupyter Notebooks.  Traditionally, this application runs kernels locally, but it too
   can be configured to redirect kernel management to a Gateway server.
 - `Jupyter Kernel Gateway <https://jupyter-kernel-gateway.readthedocs.io/en/latest/>`_ - a web
   server that provides headless access to Jupyter kernels.  A Gateway server itself, all kernels
   are launched from this server into their respective remote clusters.  It is via a Gateway server
   that users are able to *disconnect* their local server from the remote cluster to access different
   compute resources.

.. admonition:: Use cases

    - *As a data scientist, I want to run my notebook remotely on my local cluster so that I can free up resources on my own laptop and perform compute-intensive operations on the other, more performant nodes of my cluster.*

    - *As a student, my Data Science 101 course is leveraging GPUs in our experiments.  Since GPUs are expensive, we must share resources within the university's compute cluster and configure our Notebooks to leverage the department's Gateway server, which can then spawn container-based kernels that have access to a GPU on Kubernetes.*

.. toctree::
   :maxdepth: 1
   :name: users


   connecting-to-a-gateway
   kernel-envs
