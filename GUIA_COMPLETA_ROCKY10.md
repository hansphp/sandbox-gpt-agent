# Guía completa: instalar sandbox-gpt-agent en Rocky Linux 10

## Objetivo

Esta guia instala `sandbox-gpt-agent` en un VPS Rocky Linux 10 como despliegue de referencia para un agente tecnologico de proposito general conectado mediante GPT Actions.

La interfaz es generica. No programa scripts especificos de capturas, scrapers o aplicaciones. Sirve como control plane para que el GPT pueda crear codigo, ejecutar tareas, leer salidas, descargar artefactos, modificar archivos, diagnosticar servicios y preparar laboratorios tecnologicos en solicitudes futuras.

## Arquitectura

```text
Usuario
  ↓
Custom GPT privado
  ↓ GPT Actions / OpenAPI
https://agent.tudominio.com
  ↓ Nginx + TLS
127.0.0.1:8765
  ↓
sandbox-gpt-agent.service
  ↓
Rocky Linux 10 VPS
```

El servicio escucha localmente en `127.0.0.1:8765`. Nginx publica la API por HTTPS en puerto 443. El GPT usa API Key tipo Bearer.

## Qué capacidades expone

- Ejecutar cualquier comando Linux mediante `/bin/bash -lc`.
- Ejecutar procesos largos en background.
- Consultar stdout/stderr de jobs.
- Crear, leer, listar, borrar y cambiar permisos de archivos.
- Subir archivos mediante HTTP raw upload.
- Importar archivos subidos al chat con `openaiFileIdRefs`.
- Devolver archivos no imagen con `openaiFileResponse`.
- Crear enlaces temporales públicos para imágenes o binarios grandes.
- Consultar auditoría y estado del sistema.

## Requisitos

- VPS con Rocky Linux 10.
- Acceso root o sudo.
- Dominio o subdominio apuntando al VPS.
- Puertos 80 y 443 abiertos en el proveedor cloud.
- `firewalld` opcional; el script abre HTTP/HTTPS si está activo.

## Instalación del agente

Sube el paquete al VPS:

```bash
scp sandbox-gpt-agent.tar.gz root@IP_DEL_VPS:/tmp/
```

Entra al VPS:

```bash
ssh root@IP_DEL_VPS
cd /tmp
tar xzf sandbox-gpt-agent.tar.gz
cd sandbox-gpt-agent
sudo bash install.sh
```

El instalador crea:

```text
/opt/sandbox-gpt-agent/agent.py
/etc/sandbox-gpt-agent.env
/etc/systemd/system/sandbox-gpt-agent.service
/srv/sandbox-gpt-agent/workspace
/var/lib/sandbox-gpt-agent
/var/log/sandbox-gpt-agent/audit.log
```

También imprime un token. Guárdalo porque será la API Key Bearer del GPT.

## Verificación local

```bash
systemctl status sandbox-gpt-agent
curl -s http://127.0.0.1:8765/health
bash smoke-test.sh
```

Prueba manual:

```bash
TOKEN="$(grep '^SANDBOX_TOKEN=' /etc/sandbox-gpt-agent.env | cut -d= -f2-)"

curl -s -X POST http://127.0.0.1:8765/v1/exec \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"command":"id && uname -a && pwd"}'
```

## Publicar con Nginx + HTTPS

Primero apunta un registro DNS al VPS:

```text
agent.tudominio.com  A  IP_DEL_VPS
```

Luego ejecuta:

```bash
DOMAIN=agent.tudominio.com EMAIL=tu@email.com sudo -E bash setup-nginx-https.sh
```

El script instala Nginx, Certbot, configura reverse proxy, habilita HTTPS y actualiza `SANDBOX_PUBLIC_BASE_URL`.

URLs esperadas:

```text
https://agent.tudominio.com/health
https://agent.tudominio.com/gpt-action-openapi.yaml
https://agent.tudominio.com/privacy
```

## Configurar el Custom GPT

1. Abre ChatGPT.
2. Entra a **Explore GPTs**.
3. Selecciona **Create**.
4. Ve a **Configure**.
5. Nombre sugerido: `Technology Operator`.
6. Descripcion sugerida: `Opera un entorno tecnologico controlado mediante Actions para ejecutar comandos, gestionar archivos, diagnosticar servicios y generar artefactos.`
7. Copia el contenido de `CUSTOM_GPT_INSTRUCTIONS.md` en **Instructions**.
8. En **Actions**, crea una nueva acción.
9. Authentication: **API Key**.
10. Auth type: **Bearer**.
11. Token: usa `SANDBOX_TOKEN` de `/etc/sandbox-gpt-agent.env`.
12. Schema: importa `https://agent.tudominio.com/gpt-action-openapi.yaml`.
13. Privacy Policy URL: `https://agent.tudominio.com/privacy`.
14. En Preview, prueba `healthCheck`, `getSystemInfo` y `runCommand`.

## Ejemplos de uso de la API

Define variables:

```bash
HOST="https://agent.tudominio.com"
TOKEN="TU_TOKEN"
```

Ejecutar comando:

```bash
curl -s -X POST "$HOST/v1/exec" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"command":"id && pwd && ls -la"}'
```

Ejecutar job largo:

```bash
curl -s -X POST "$HOST/v1/exec" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"command":"dnf install -y git && git --version","background":true,"timeout":900}'
```

Consultar job:

```bash
curl -s "$HOST/v1/jobs/JOB_ID?tail_bytes=60000" \
  -H "Authorization: Bearer $TOKEN"
```

Crear archivo:

```bash
curl -s -X POST "$HOST/v1/files/write" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"path":"demo/hello.py","content":"print(\"hola\")\n","encoding":"text"}'
```

Ejecutarlo:

```bash
curl -s -X POST "$HOST/v1/exec" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"command":"python3 demo/hello.py"}'
```

Subir archivo raw desde tu máquina:

```bash
curl -s -X PUT "$HOST/v1/files/raw?path=uploads/archivo.bin" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary "@archivo.bin"
```

Descargar archivo autenticado:

```bash
curl -L "$HOST/v1/files/download?path=uploads/archivo.bin" \
  -H "Authorization: Bearer $TOKEN" \
  -o archivo.bin
```

Crear URL temporal pública:

```bash
curl -s -X POST "$HOST/v1/files/share" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"path":"outputs/resultado.png","ttl_seconds":3600,"max_downloads":3}'
```

## Cómo usar archivos subidos en ChatGPT

Cuando el usuario suba un archivo al chat, el GPT debe llamar:

```text
importOpenAIConversationFiles
```

El endpoint recibe `openaiFileIdRefs` y descarga los archivos al workspace del agente. Después el GPT puede inspeccionarlos con `listFiles`, `readFile`, `statFile` o comandos Linux.

## Cómo devolver resultados

Para texto y archivos no imagen menores de 10 MB:

```text
returnFilesToChatGPT
```

Para imágenes, videos o binarios grandes:

```text
shareFile
```

Esto produce una URL temporal pública. Es lo correcto para capturas de pantalla, archivos `.png`, `.jpg`, `.mp4`, `.zip` grandes o artefactos de build.

## Variables de configuración

Edita:

```bash
sudo nano /etc/sandbox-gpt-agent.env
sudo systemctl restart sandbox-gpt-agent
```

Variables principales:

```text
SANDBOX_TOKEN=...
SANDBOX_BIND=127.0.0.1
SANDBOX_PORT=8765
SANDBOX_PUBLIC_BASE_URL=https://agent.tudominio.com
SANDBOX_WORKDIR=/srv/sandbox-gpt-agent/workspace
SANDBOX_ALLOW_ABSOLUTE=1
SANDBOX_DEFAULT_TIMEOUT=40
SANDBOX_MAX_TIMEOUT=3600
SANDBOX_MAX_SYNC_OUTPUT_BYTES=61440
SANDBOX_MAX_READ_BYTES=1048576
SANDBOX_RATE_LIMIT_PER_MIN=120
SANDBOX_ACTIONS_CONSEQUENTIAL=false
```

`SANDBOX_ACTIONS_CONSEQUENTIAL=false` permite que el GPT use “always allow” más fácilmente. Si prefieres confirmación obligatoria para comandos y mutaciones, cambia a:

```text
SANDBOX_ACTIONS_CONSEQUENTIAL=true
```

Luego reinicia el servicio y vuelve a importar el schema en el GPT.

## Logs y auditoría

Ver logs del servicio:

```bash
journalctl -u sandbox-gpt-agent -n 100 --no-pager
```

Ver auditoría:

```bash
tail -n 100 /var/log/sandbox-gpt-agent/audit.log
```

Desde el GPT:

```text
tailAuditLog
```

## Rotar token

```bash
sudo bash rotate-token.sh
```

Después actualiza el token en la configuración de Authentication de la Action.

## Desinstalar

```bash
sudo bash uninstall.sh
```

El desinstalador quita el servicio y `/opt/sandbox-gpt-agent`. Conserva estado, workspace, logs y env para evitar borrar accidentalmente proyectos.

## Notas de seguridad

El servicio es una API de ejecución remota de comandos. Instálalo únicamente en un entorno controlado. Mantén HTTPS, token fuerte, snapshots, auditoría y un dominio dedicado. No guardes secretos reales de producción dentro del workspace del agente.
