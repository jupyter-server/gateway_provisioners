Welcome to Gateway Provisioners!
================================
Gateway Provisioners provides a pluggable framework for remote kernels leveraging
`Kernel Provisioners <https://jupyter-client.readthedocs.io/en/latest/provisioning.html>`_ introduced
in recent versions of Jupyter Client (7.0+).  Many of the Kernel Provisioners provided by
Gateway Provisioners are
based on the same functionality introduced in `Enterprise Gateway's process proxy architecture
<https://jupyter-enterprise-gateway.readthedocs.io/en/latest/contributors/system-architecture.html#process-proxy>`_,
the difference being that Kernel Provisioners do not require the override of the ``KernelManager``
class hierarchy, allowing *any* application that uses the ``jupyter_client`` package for its kernel
management to leverage these remote kernels.

By default, the Jupyter framework runs kernels locally - potentially exhausting the
server of resources. By leveraging the functionality of the underlying resource management
applications like Hadoop YARN, Kubernetes, and others, the Gateway Provisioners package
distributes kernels across the compute cluster, dramatically increasing the number of
simultaneously active kernels while leveraging the available compute resources.

Who's this for?
---------------
In these docs, we've attempted to keep the role-based organizational structure used in Jupyter Server and
Jupyter Enterprise Gateway.  As in the other repositories, actual usage can span the roles, so we recommend
becoming familiar with the roles in which you are most impacted.  These roles are roughly defined as follows:

1. `Users <users/index.html>`_: people using Jupyter web applications that wish to use Gateway Provisioners.
2. `Operators <operators/index.html>`_: people deploying or serving Jupyter applications that wish to leverage Gateway Provisioners.
3. `Developers <developers/index.html>`_: people writing applications or deploying kernels for other resource managers.
4. `Contributors <contributors/index.html>`_: people contributing directly to the Gateway Provisioners project.

If you find gaps in our documentation, please open an issue (or better yet, a pull request) on the
Gateway Provisioners `Github repo <https://github.com/gateway-experiments/gateway_provisioners>`_.

.. note::
   The following pages are still in transition from the `Jupyter Enterprise Gateway repository
   <https://github.com/jupyter-server/enterprise_gateway>`_.  As a result, you will find information that pertains
   to Enterprise Gateway, but really has no application relative to Gateway Provisioners.
   Please bear with us in these busy (and exciting) times!


Table of Contents
-----------------

.. toctree::
   :maxdepth: 2

   Users <users/index>
   Operators <operators/index>
   Developers <developers/index>
   Contributors <contributors/index>
