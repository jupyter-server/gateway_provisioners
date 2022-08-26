# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
"""Mixin for configuation options on RemoteProvisionerBase."""

import os

from tornado.log import LogFormatter

from traitlets import default, Set, Unicode, Bool, Integer
from traitlets.config import Configurable


# Commonly used envs
max_poll_attempts = int(os.getenv('RP_MAX_POLL_ATTEMPTS', '10'))
poll_interval = float(os.getenv('RP_POLL_INTERVAL', '0.5'))
socket_timeout = float(os.getenv('RP_SOCKET_TIMEOUT', '0.005'))
ssh_port = int(os.getenv('RP_SSH_PORT', '22'))


class RemoteProvisionerConfigMixin(Configurable):

    _log_formatter_cls = LogFormatter  # traitlet default is LevelFormatter

    @default('log_format')
    def _default_log_format(self):
        """override default log format to include milliseconds"""
        return u"%(color)s[%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s]%(end_color)s %(message)s"

    # Unauthorized users
    unauthorized_users_env = 'RP_UNAUTHORIZED_USERS'
    unauthorized_users_default_value = 'root'
    unauthorized_users = Set(default_value={unauthorized_users_default_value}, config=True,
                             help="""Comma-separated list of user names (e.g., ['root','admin']) against which
                             KERNEL_USERNAME will be compared.  Any match (case-sensitive) will prevent the
                             kernel's launch and result in an HTTP 403 (Forbidden) error.
                             (RP_UNAUTHORIZED_USERS env var - non-bracketed, just comma-separated)""")

    @default('unauthorized_users')
    def unauthorized_users_default(self):
        return os.getenv(self.unauthorized_users_env, self.unauthorized_users_default_value).split(',')

    # Authorized users
    authorized_users_env = 'RP_AUTHORIZED_USERS'
    authorized_users = Set(config=True,
                           help="""Comma-separated list of user names (e.g., ['bob','alice']) against which
                           KERNEL_USERNAME will be compared.  Any match (case-sensitive) will allow the kernel's
                           launch, otherwise an HTTP 403 (Forbidden) error will be raised.  The set of unauthorized
                           users takes precedence. This option should be used carefully as it can dramatically limit
                           who can launch kernels.  (RP_AUTHORIZED_USERS env var - non-bracketed,
                           just comma-separated)""")

    @default('authorized_users')
    def authorized_users_default(self):
        au_env = os.getenv(self.authorized_users_env)
        return au_env.split(',') if au_env is not None else []

    # Port range
    port_range_env = 'RP_PORT_RANGE'
    port_range_default_value = "0..0"
    port_range = Unicode(port_range_default_value, config=True,
                         help="""Specifies the lower and upper port numbers from which ports are created.
                         The bounded values are separated by '..' (e.g., 33245..34245 specifies a range of 1000 ports
                         to be randomly selected). A range of zero (e.g., 33245..33245 or 0..0) disables port-range
                         enforcement.  (RP_PORT_RANGE env var)""")

    @default('port_range')
    def port_range_default(self):
        return os.getenv(self.port_range_env, self.port_range_default_value)

    # Conductor endpoint - TODO: Move to ConductorProvisioner
    conductor_endpoint_env = 'RP_CONDUCTOR_ENDPOINT'
    conductor_endpoint_default_value = None
    conductor_endpoint = Unicode(conductor_endpoint_default_value,
                                 allow_none=True,
                                 config=True,
                                 help="""The http url for accessing the Conductor REST API.
                                 (RP_CONDUCTOR_ENDPOINT env var)""")

    @default('conductor_endpoint')
    def conductor_endpoint_default(self):
        return os.getenv(self.conductor_endpoint_env, self.conductor_endpoint_default_value)

    # Impersonation enabled - TODO - Applies to Yarn/Conductor?
    impersonation_enabled_env = 'RP_IMPERSONATION_ENABLED'
    impersonation_enabled = Bool(False, config=True,
                                 help="""Indicates whether impersonation will be performed during kernel launch.
                                 (RP_IMPERSONATION_ENABLED env var)""")

    @default('impersonation_enabled')
    def impersonation_enabled_default(self):
        return bool(os.getenv(self.impersonation_enabled_env, 'false').lower() == 'true')

    launch_timeout_env = 'RP_LAUNCH_TIMEOUT'
    launch_timeout_default_value = 30
    launch_timeout = Integer(launch_timeout_default_value, config=True,
                           help="""Number of ports to try if the specified port is not available
                           (RP_LAUNCH_TIMEOUT env var)""")

    @default('launch_timeout')
    def launch_timeout_default(self):
        return int(os.getenv(self.launch_timeout_env,
                             os.getenv('KERNEL_LAUNCH_TIMEOUT', self.launch_timeout_default_value)))
