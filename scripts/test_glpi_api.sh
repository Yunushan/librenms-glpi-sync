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

AUTH_ARGS=()
if [[ "${GLPI_AUTH_METHOD:-basic}" == "basic" ]]; then
  AUTH_ARGS=(-u "${GLPI_USERNAME}:${GLPI_PASSWORD}")
else
  AUTH_ARGS=(-H "Authorization: user_token ${GLPI_USER_TOKEN}")
fi

SESSION_JSON="$(
  curl "${CURL_OPTS[@]}" -X GET \
    "${HEADERS[@]}" \
    "${AUTH_ARGS[@]}" \
    "${GLPI_URL}/apirest.php/initSession/"
)"

echo "initSession:"
echo "${SESSION_JSON}"

SESSION_TOKEN="$(
  python3 - <<'PY' "${SESSION_JSON}"
import json
import sys
data = json.loads(sys.argv[1])
print(data.get("session_token", ""))
PY
)"

if [[ -z "${SESSION_TOKEN}" ]]; then
  echo "Could not extract session_token from initSession response" >&2
  exit 1
fi

API_HEADERS=("${HEADERS[@]}" -H "Session-Token: ${SESSION_TOKEN}")

if [[ -n "${GLPI_PROFILE_ID:-}" ]]; then
  echo
  echo "changeActiveProfile:"
  curl "${CURL_OPTS[@]}" -X POST \
    "${API_HEADERS[@]}" \
    -d "{\"profiles_id\": ${GLPI_PROFILE_ID}}" \
    "${GLPI_URL}/apirest.php/changeActiveProfile/"
  echo
fi

if [[ -n "${GLPI_ENTITY_ID:-}" ]]; then
  echo
  echo "changeActiveEntities:"
  curl "${CURL_OPTS[@]}" -X POST \
    "${API_HEADERS[@]}" \
    -d "{\"entities_id\": ${GLPI_ENTITY_ID}, \"is_recursive\": true}" \
    "${GLPI_URL}/apirest.php/changeActiveEntities/"
  echo
fi

echo
echo "getActiveProfile:"
curl "${CURL_OPTS[@]}" -X GET \
  "${API_HEADERS[@]}" \
  "${GLPI_URL}/apirest.php/getActiveProfile/"
echo

echo
echo "getMyProfiles:"
curl "${CURL_OPTS[@]}" -X GET \
  "${API_HEADERS[@]}" \
  "${GLPI_URL}/apirest.php/getMyProfiles/"
echo

echo
echo "getActiveEntities:"
curl "${CURL_OPTS[@]}" -X GET \
  "${API_HEADERS[@]}" \
  "${GLPI_URL}/apirest.php/getActiveEntities/"
echo

echo
echo "getMyEntities:"
curl "${CURL_OPTS[@]}" -X GET \
  "${API_HEADERS[@]}" \
  "${GLPI_URL}/apirest.php/getMyEntities/"
echo

echo
echo "killSession:"
curl "${CURL_OPTS[@]}" -X GET \
  "${API_HEADERS[@]}" \
  "${GLPI_URL}/apirest.php/killSession/"
echo
