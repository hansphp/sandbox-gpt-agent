#!/usr/bin/env bash
set -euo pipefail
APP_NAME="sandbox-gpt-agent"
HOST="${HOST:-http://127.0.0.1:8765}"
TOKEN="${TOKEN:-$(grep '^SANDBOX_TOKEN=' /etc/${APP_NAME}.env | cut -d= -f2-)}"

echo "== health =="
curl -s "${HOST}/health"; echo

echo "== sys info =="
curl -s "${HOST}/v1/sys/info" -H "Authorization: Bearer ${TOKEN}"; echo

echo "== exec =="
curl -s -X POST "${HOST}/v1/exec" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"command":"id && uname -a && pwd"}'; echo

echo "== write/read =="
curl -s -X POST "${HOST}/v1/files/write" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H 'Content-Type: application/json' \
  -d '{"path":"smoke/hello.txt","content":"hola desde sandbox-gpt-agent\n","encoding":"text"}'; echo
curl -s "${HOST}/v1/files/read?path=smoke/hello.txt" -H "Authorization: Bearer ${TOKEN}"; echo
