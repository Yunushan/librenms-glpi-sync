#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ENV_FILE:-}" ]]; then
  ENV_FILE="/etc/librenms-glpi-sync.env"
fi

set -a
source "$ENV_FILE"
set +a

curl --silent --show-error \
  -H "X-Auth-Token: ${LIBRENMS_TOKEN}" \
  "${LIBRENMS_URL%/}/api/v0/devices?type=${LIBRENMS_DEVICE_FILTER:-active}&order=$(python3 - <<'PY'
import os, urllib.parse
print(urllib.parse.quote(os.environ.get('LIBRENMS_DEVICE_ORDER', 'hostname ASC')))
PY
)"
