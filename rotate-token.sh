#!/usr/bin/env bash
set -euo pipefail
APP_NAME="sandbox-gpt-agent"
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash rotate-token.sh" >&2
  exit 1
fi
TOKEN="$(openssl rand -hex 32)"
if grep -q '^SANDBOX_TOKEN=' /etc/${APP_NAME}.env; then
  sed -i "s/^SANDBOX_TOKEN=.*/SANDBOX_TOKEN=${TOKEN}/" /etc/${APP_NAME}.env
else
  echo "SANDBOX_TOKEN=${TOKEN}" >> /etc/${APP_NAME}.env
fi
chmod 0600 /etc/${APP_NAME}.env
systemctl restart ${APP_NAME}
echo "New token: ${TOKEN}"
