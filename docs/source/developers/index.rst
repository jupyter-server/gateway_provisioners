Developers Guide
================

These pages target *developers* authoring gateway provisioners for other resource managers, or integrating
applications with remote kernel functionality.

.. admonition:: Use cases

    - *As a developer, I want to explore supporting a different resource manager by implementing a new Gateway Provisioner such that I can easily take advantage of specific functionality provided by the resource manager.*
    - *As a developer, I want to easily integrate the ability to launch remote kernels with existing platforms, so I can leverage my compute cluster in a customizable way.*
    - *As a developer, I am currently using Golang and need to implement a kernel launcher to allow the Go kernel I use to run remotely in my Kubernetes cluster.*
    - *As a developer, I'd like to extend some of the kernel container images and, eventually, create my own to better enable the data scientists I support.*

.. toctree::
   :maxdepth: 1
   :name: developers

   dev-remote-provisioner
   kernel-launcher
   kernel-specification
   custom-images
   API Docs <../api/modules>
