#!/usr/bin/env bash
set -euo pipefail
APP_NAME="sandbox-gpt-agent"
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash uninstall.sh" >&2
  exit 1
fi
systemctl disable --now ${APP_NAME} 2>/dev/null || true
rm -f /etc/systemd/system/${APP_NAME}.service
systemctl daemon-reload
rm -rf /opt/${APP_NAME}
echo "Removed service and /opt/${APP_NAME}. Kept /etc/${APP_NAME}.env, /srv/${APP_NAME}, /var/lib/${APP_NAME}, and /var/log/${APP_NAME}."
