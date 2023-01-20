# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
###
# NOTE: This is a placeholder file to satisfy references in the corresponding launch_ipykernel.py
# file.  It will be replaced with the file in ../../shared/server_listener.py during kernel-launcher
# assembly.  The file is also used by the launch_IRkernel.R script, but it does not require a
# placeholder to satisfy references due to the language differences.
#
from typing import Optional


def setup_server_listener(
    conn_filename: str,
    parent_pid: int,
    lower_port: int,
    upper_port: int,
    response_addr: str,
    kernel_id: str,
    public_key: str,
    cluster_type: Optional[str] = None,
    as_thread: Optional[bool] = True,
):
    err_msg = "kernel-launcher assembly is required!"
    raise NotImplementedError(err_msg)
