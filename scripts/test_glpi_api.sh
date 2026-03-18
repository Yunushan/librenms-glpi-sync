#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-/etc/librenms-glpi-sync.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

CURL_OPTS=(-sS)
if [[ "${GLPI_VERIFY_TLS:-true}" == "false" ]]; then
  CURL_OPTS+=(-k)
fi
HEADERS=(-H "Content-Type: application/json")

if [[ -n "${GLPI_APP_TOKEN:-}" ]]; then
  HEADERS+=(-H "App-Token: ${GLPI_APP_TOKEN}")
fi

if [[ "${GLPI_AUTH_METHOD:-basic}" == "basic" ]]; then
  curl "${CURL_OPTS[@]}" -X GET \
    "${HEADERS[@]}" \
    -u "${GLPI_USERNAME}:${GLPI_PASSWORD}" \
    "${GLPI_URL}/apirest.php/initSession"
else
  curl "${CURL_OPTS[@]}" -X GET \
    "${HEADERS[@]}" \
    -H "Authorization: user_token ${GLPI_USER_TOKEN}" \
    "${GLPI_URL}/apirest.php/initSession"
fi
