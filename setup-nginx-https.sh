#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash setup-nginx-https.sh" >&2
  exit 1
fi

APP_NAME="sandbox-gpt-agent"
DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
PORT="${SANDBOX_PORT:-8765}"

if [[ -z "${DOMAIN}" || -z "${EMAIL}" ]]; then
  echo "Usage: DOMAIN=agent.example.com EMAIL=you@example.com sudo -E bash setup-nginx-https.sh" >&2
  exit 1
fi

if ! command -v dnf >/dev/null 2>&1; then
  echo "dnf not found. This script targets Rocky Linux 10 / RHEL-compatible systems." >&2
  exit 1
fi

# EPEL normally provides Certbot packages on Rocky/RHEL-compatible systems.
dnf install -y epel-release >/dev/null || true
dnf install -y nginx certbot python3-certbot-nginx policycoreutils-python-utils >/dev/null

mkdir -p /etc/nginx/conf.d
cat > /etc/nginx/conf.d/${APP_NAME}.conf <<EOF_NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 0;

    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Authorization \$http_authorization;
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }
}
EOF_NGINX

# Allow nginx/httpd context to proxy to localhost when SELinux is enforcing.
if command -v setsebool >/dev/null 2>&1; then
  setsebool -P httpd_can_network_connect 1 || true
fi

systemctl enable --now nginx >/dev/null
nginx -t
systemctl reload nginx

if systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-service=http >/dev/null || true
  firewall-cmd --permanent --add-service=https >/dev/null || true
  firewall-cmd --reload >/dev/null || true
fi

certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos -m "${EMAIL}" --redirect

# Persist public base URL for generated OpenAPI and shared links.
if [[ -f /etc/${APP_NAME}.env ]]; then
  if grep -q '^SANDBOX_PUBLIC_BASE_URL=' /etc/${APP_NAME}.env; then
    sed -i "s|^SANDBOX_PUBLIC_BASE_URL=.*|SANDBOX_PUBLIC_BASE_URL=https://${DOMAIN}|" /etc/${APP_NAME}.env
  else
    echo "SANDBOX_PUBLIC_BASE_URL=https://${DOMAIN}" >> /etc/${APP_NAME}.env
  fi
  systemctl restart ${APP_NAME}
fi

cat <<EOF_OUT

HTTPS configured.

Base URL: https://${DOMAIN}
Health: https://${DOMAIN}/health
OpenAPI schema: https://${DOMAIN}/gpt-action-openapi.yaml
Privacy URL: https://${DOMAIN}/privacy

Use API Key authentication in GPT Actions:
  Type: Bearer
  Token: see /etc/${APP_NAME}.env, variable SANDBOX_TOKEN
EOF_OUT
