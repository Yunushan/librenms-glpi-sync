#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ENV_FILE:-}" ]]; then
  ENV_FILE="/etc/librenms-glpi-sync.env"
fi

set -a
source "$ENV_FILE"
set +a

curl_args=(--silent --show-error)
if [[ "${GLPI_VERIFY_TLS:-true}" != "true" ]]; then
  curl_args+=(--insecure)
fi

if [[ "${GLPI_AUTH_METHOD:-basic}" == "basic" ]]; then
  curl "${curl_args[@]}" -u "${GLPI_USERNAME}:${GLPI_PASSWORD}" \
    "${GLPI_URL%/}/apirest.php/initSession/"
else
  headers=(-H "Authorization: user_token ${GLPI_USER_TOKEN}")
  if [[ -n "${GLPI_APP_TOKEN:-}" ]]; then
    headers+=(-H "App-Token: ${GLPI_APP_TOKEN}")
  fi
  curl "${curl_args[@]}" "${headers[@]}" \
    "${GLPI_URL%/}/apirest.php/initSession/"
fi
