#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/librenms-glpi-sync"
ENV_FILE="/etc/librenms-glpi-sync.env"
STATE_DIR="/var/lib/librenms-glpi-sync"
ENABLE_TIMER="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --state-dir)
      STATE_DIR="$2"
      shift 2
      ;;
    --enable-timer)
      ENABLE_TIMER="true"
      shift
      ;;
    -h|--help)
      cat <<USAGE
Usage: sudo ./install.sh [options]

Options:
  --install-dir PATH   Default: /opt/librenms-glpi-sync
  --env-file PATH      Default: /etc/librenms-glpi-sync.env
  --state-dir PATH     Default: /var/lib/librenms-glpi-sync
  --enable-timer       Enable and start the systemd timer after install
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$INSTALL_DIR" "$STATE_DIR"

install -m 0755 "$SCRIPT_DIR/sync.py" "$INSTALL_DIR/sync.py"
install -m 0644 "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
cp -r "$SCRIPT_DIR/scripts" "$INSTALL_DIR/" 2>/dev/null || true

python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip >/dev/null
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0600 "$SCRIPT_DIR/.env.example" "$ENV_FILE"
  sed -i "s#^STATE_FILE=.*#STATE_FILE=${STATE_DIR}/state.json#" "$ENV_FILE"
  echo "Created $ENV_FILE from .env.example"
else
  echo "Keeping existing $ENV_FILE"
fi

mkdir -p /etc/systemd/system
sed \
  -e "s#__INSTALL_DIR__#${INSTALL_DIR}#g" \
  -e "s#__ENV_FILE__#${ENV_FILE}#g" \
  "$SCRIPT_DIR/systemd/librenms-glpi-sync.service" \
  > /etc/systemd/system/librenms-glpi-sync.service
install -m 0644 "$SCRIPT_DIR/systemd/librenms-glpi-sync.timer" /etc/systemd/system/librenms-glpi-sync.timer

chmod 600 "$ENV_FILE"
systemctl daemon-reload

cat <<MSG

Install complete.

Next steps:
  1) Edit $ENV_FILE
  2) Test LibreNMS API:
     ${INSTALL_DIR}/scripts/test_librenms_api.sh
  3) Test GLPI API:
     ${INSTALL_DIR}/scripts/test_glpi_api.sh
  4) Run one test sync:
     set -a; source ${ENV_FILE}; ONLY_HOST=your-device ${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/sync.py
  5) Run full sync:
     set -a; source ${ENV_FILE}; ${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/sync.py
MSG

if [[ "$ENABLE_TIMER" == "true" ]]; then
  systemctl enable --now librenms-glpi-sync.timer
  echo "Timer enabled: librenms-glpi-sync.timer"
else
  echo "Timer not enabled. Enable later with: systemctl enable --now librenms-glpi-sync.timer"
fi
