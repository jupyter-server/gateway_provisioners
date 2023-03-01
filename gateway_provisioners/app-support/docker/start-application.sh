#!/bin/bash

APP_CMD=${APP_CMD:-"jupyter-kernelgateway"}
APP_NAME=${APP_NAME:-"Jupyter Kernel Gateway"}

# Gateway Provisioner variables
export GP_SSH_PORT=${GP_SSH_PORT:-2122}

# To use tunneling set this variable to 'True' (may need to run as root).
export GP_ENABLE_TUNNELING=${GP_ENABLE_TUNNELING:-False}

additional_options=""
if [ "${APP_CMD}" == "jupyter-lab" ]; then
  additional_options+="--ServerApp.open_browser=False --ServerApp.ip=0.0.0.0 "
else
  # Gateway applications need to enable list kernel functionality
  export KG_LIST_KERNELS=True
  export KG_IP="0.0.0.0"
fi

export APP_LOG_LEVEL=${APP_LOG_LEVEL:-DEBUG}
export APP_CULL_IDLE_TIMEOUT=${APP_CULL_IDLE_TIMEOUT:-43200}  # default to 12 hours
export APP_CULL_INTERVAL=${APP_CULL_INTERVAL:-60}
export APP_CULL_CONNECTED=${APP_CULL_CONNECTED:-False}
APP_ALLOWED_KERNELS=${APP_ALLOWED_KERNELS:-"null"}
# sed is used to strip off surrounding brackets and quotes as they should no longer be included.
export APP_ALLOWED_KERNELS=`echo ${APP_ALLOWED_KERNELS} | sed 's/[][]//g' | sed 's/\"//g'`
export APP_DEFAULT_KERNEL_NAME=${APP_DEFAULT_KERNEL_NAME:-docker_python}

# Determine whether the kernels-allowed list should be added to the start command.
# This is conveyed via a 'null' value for the env - which indicates no kernel names
# were used in the helm chart or docker-compose yaml.

if [ "${APP_ALLOWED_KERNELS}" != "null" ]; then
  OIFS=$IFS
  IFS=,
  for ks in $APP_ALLOWED_KERNELS
  do
    additional_options+="--KernelSpecManager.allowed_kernelspecs=${ks} "
  done
  IFS=$OIFS
fi

echo "Starting ${APP_NAME}..."
echo exec ${APP_CMD} \
	--log-level=${APP_LOG_LEVEL} ${additional_options} \
	--MappingKernelManager.cull_idle_timeout=${APP_CULL_IDLE_TIMEOUT} \
	--MappingKernelManager.cull_interval=${APP_CULL_INTERVAL} \
	--MappingKernelManager.cull_connected=${APP_CULL_CONNECTED} \
	--MappingKernelManager.default_kernel_name=${APP_DEFAULT_KERNEL_NAME}

exec ${APP_CMD} \
	--log-level=${APP_LOG_LEVEL} ${additional_options} \
	--MappingKernelManager.cull_idle_timeout=${APP_CULL_IDLE_TIMEOUT} \
	--MappingKernelManager.cull_interval=${APP_CULL_INTERVAL} \
	--MappingKernelManager.cull_connected=${APP_CULL_CONNECTED} \
	--MappingKernelManager.default_kernel_name=${APP_DEFAULT_KERNEL_NAME}
