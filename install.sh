#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash install.sh" >&2
  exit 1
fi

APP_NAME="sandbox-gpt-agent"
INSTALL_DIR="${INSTALL_DIR:-/opt/${APP_NAME}}"
WORKDIR="${SANDBOX_WORKDIR:-/srv/${APP_NAME}/workspace}"
STATE_DIR="${SANDBOX_STATE_DIR:-/var/lib/${APP_NAME}}"
LOG_DIR="${SANDBOX_LOG_DIR:-/var/log/${APP_NAME}}"
PORT="${SANDBOX_PORT:-8765}"
BIND="${SANDBOX_BIND:-127.0.0.1}"
PUBLIC_BASE_URL="${SANDBOX_PUBLIC_BASE_URL:-}"
ALLOW_ABSOLUTE="${SANDBOX_ALLOW_ABSOLUTE:-1}"
DEFAULT_TIMEOUT="${SANDBOX_DEFAULT_TIMEOUT:-40}"
MAX_TIMEOUT="${SANDBOX_MAX_TIMEOUT:-3600}"
MAX_SYNC_OUTPUT_BYTES="${SANDBOX_MAX_SYNC_OUTPUT_BYTES:-61440}"
MAX_READ_BYTES="${SANDBOX_MAX_READ_BYTES:-1048576}"
MAX_IMPORT_FILE_BYTES="${SANDBOX_MAX_IMPORT_FILE_BYTES:-536870912}"
MAX_EXPORT_FILE_BYTES="${SANDBOX_MAX_EXPORT_FILE_BYTES:-9437184}"
RATE_LIMIT_PER_MIN="${SANDBOX_RATE_LIMIT_PER_MIN:-120}"
ACTIONS_CONSEQUENTIAL="${SANDBOX_ACTIONS_CONSEQUENTIAL:-false}"
PRIVACY_CONTACT="${SANDBOX_PRIVACY_CONTACT:-sandbox owner}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" != "rocky" ]]; then
    echo "Warning: this installer is tuned for Rocky Linux 10; detected ID=${ID:-unknown}. Continuing." >&2
  elif [[ "${VERSION_ID:-}" != 10* ]]; then
    echo "Warning: this installer is tuned for Rocky Linux 10; detected VERSION_ID=${VERSION_ID:-unknown}. Continuing." >&2
  fi
fi

if ! command -v dnf >/dev/null 2>&1; then
  echo "dnf not found. This installer targets Rocky Linux 10 / RHEL-compatible systems." >&2
  exit 1
fi

# Minimal base packages. Do not run a full system upgrade automatically.
dnf install -y python3 python3-pip ca-certificates curl openssl tar gzip >/dev/null

mkdir -p "${INSTALL_DIR}" "${WORKDIR}" "${STATE_DIR}" "${LOG_DIR}"
cp "${SCRIPT_DIR}/agent.py" "${INSTALL_DIR}/agent.py"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/requirements.txt"
chmod 0755 "${INSTALL_DIR}"
chmod 0644 "${INSTALL_DIR}/agent.py" "${INSTALL_DIR}/requirements.txt"

# Create a virtual environment. On Rocky/RHEL this usually works with python3 directly.
if [[ ! -x "${INSTALL_DIR}/.venv/bin/python" ]]; then
  if ! python3 -m venv "${INSTALL_DIR}/.venv"; then
    echo "python3 -m venv failed. Trying python3-virtualenv package." >&2
    dnf install -y python3-virtualenv >/dev/null || true
    if command -v virtualenv >/dev/null 2>&1; then
      virtualenv -p python3 "${INSTALL_DIR}/.venv"
    else
      echo "Could not create Python virtualenv. Install python3-virtualenv and rerun." >&2
      exit 1
    fi
  fi
fi

"${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip wheel >/dev/null
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt" >/dev/null

TOKEN="${SANDBOX_TOKEN:-}"
if [[ -z "${TOKEN}" ]]; then
  TOKEN="$(openssl rand -hex 32)"
fi

cat > /etc/${APP_NAME}.env <<EOF_ENV
SANDBOX_TOKEN=${TOKEN}
SANDBOX_BIND=${BIND}
SANDBOX_PORT=${PORT}
SANDBOX_PUBLIC_BASE_URL=${PUBLIC_BASE_URL}
SANDBOX_WORKDIR=${WORKDIR}
SANDBOX_STATE_DIR=${STATE_DIR}
SANDBOX_AUDIT_LOG=${LOG_DIR}/audit.log
SANDBOX_ALLOW_ABSOLUTE=${ALLOW_ABSOLUTE}
SANDBOX_SHELL=/bin/bash
SANDBOX_DEFAULT_TIMEOUT=${DEFAULT_TIMEOUT}
SANDBOX_MAX_TIMEOUT=${MAX_TIMEOUT}
SANDBOX_MAX_SYNC_OUTPUT_BYTES=${MAX_SYNC_OUTPUT_BYTES}
SANDBOX_MAX_READ_BYTES=${MAX_READ_BYTES}
SANDBOX_MAX_IMPORT_FILE_BYTES=${MAX_IMPORT_FILE_BYTES}
SANDBOX_MAX_EXPORT_FILE_BYTES=${MAX_EXPORT_FILE_BYTES}
SANDBOX_RATE_LIMIT_PER_MIN=${RATE_LIMIT_PER_MIN}
SANDBOX_ACTIONS_CONSEQUENTIAL=${ACTIONS_CONSEQUENTIAL}
SANDBOX_PRIVACY_CONTACT=${PRIVACY_CONTACT}
EOF_ENV
chmod 0600 /etc/${APP_NAME}.env

cat > /etc/systemd/system/${APP_NAME}.service <<EOF_SERVICE
[Unit]
Description=Sandbox GPT Agent REST API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=/etc/${APP_NAME}.env
ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn agent:app --host ${BIND} --port ${PORT} --proxy-headers
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=20
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF_SERVICE

systemctl daemon-reload
systemctl enable ${APP_NAME} >/dev/null
systemctl restart ${APP_NAME}

cat <<EOF_OUT

${APP_NAME} installed on Rocky/RHEL-compatible Linux.

Local base URL: http://127.0.0.1:${PORT}
Token: ${TOKEN}
Env file: /etc/${APP_NAME}.env
Service: ${APP_NAME}.service
Install dir: ${INSTALL_DIR}
Workspace: ${WORKDIR}
Audit log: ${LOG_DIR}/audit.log

Local test:
  curl -s http://127.0.0.1:${PORT}/health
  curl -s -X POST http://127.0.0.1:${PORT}/v1/exec \\
    -H 'Authorization: Bearer ${TOKEN}' \\
    -H 'Content-Type: application/json' \\
    -d '{"command":"id && uname -a && pwd"}'

For GPT Actions with HTTPS:
  DOMAIN=agent.example.com EMAIL=you@example.com sudo -E bash setup-nginx-https.sh
EOF_OUT
