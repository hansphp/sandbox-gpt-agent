# sandbox-gpt-agent

Servicio REST auditable para convertir un entorno tecnologico controlado en un agente operable por un Custom GPT mediante GPT Actions.

El agente expone una API protegida con Bearer token para ejecutar comandos, gestionar archivos, controlar jobs, importar/exportar artefactos y publicar enlaces temporales de descarga. La instalacion incluida esta orientada a Rocky/RHEL como referencia inicial, pero la vision del proyecto es servir como base para un agente tecnologico de proposito general.

Casos de uso esperados:

- Administrar un workspace tecnico en un servidor o contenedor controlado.
- Instalar y probar software, runtimes, APIs, servicios y herramientas.
- Automatizar diagnosticos, builds, pruebas, reportes y generacion de artefactos.
- Preparar laboratorios para IaC, seguridad, datos, navegacion, integraciones o IA local.
- Conectar futuras habilidades como Cloudflare, Telegram, Playwright, correo, SSH remoto, contenedores, bases de datos u Ollama.

## Contenido

- `agent.py`: servicio FastAPI.
- `install.sh`: instala el agente en Rocky/RHEL como despliegue de referencia.
- `setup-nginx-https.sh`: publica el agente con Nginx + HTTPS + Certbot.
- `requirements.txt`: dependencias Python.
- `CUSTOM_GPT_INSTRUCTIONS.md`: instrucciones para el GPT Builder.
- `GUIA_COMPLETA_ROCKY10.md`: guia completa de instalacion y uso en Rocky Linux 10.
- `smoke-test.sh`: prueba local.
- `rotate-token.sh`: rota el Bearer token.
- `uninstall.sh`: elimina el servicio.

## Instalacion rapida

```bash
scp sandbox-gpt-agent.tar.gz root@IP_DEL_SERVIDOR:/tmp/
ssh root@IP_DEL_SERVIDOR
cd /tmp
tar xzf sandbox-gpt-agent.tar.gz
cd sandbox-gpt-agent
sudo bash install.sh
```

## Publicar para GPT Actions

Necesitas un dominio apuntando al servidor donde corre el agente.

```bash
DOMAIN=agent.tudominio.com EMAIL=tu@email.com sudo -E bash setup-nginx-https.sh
```

Luego usa en GPT Builder:

- Authentication: API Key.
- Type: Bearer.
- Token: `SANDBOX_TOKEN` de `/etc/sandbox-gpt-agent.env`.
- Schema: `https://agent.tudominio.com/gpt-action-openapi.yaml`.
- Privacy Policy URL: `https://agent.tudominio.com/privacy`.
- Instructions: copia `CUSTOM_GPT_INSTRUCTIONS.md`.

## Comandos útiles

```bash
systemctl status sandbox-gpt-agent
journalctl -u sandbox-gpt-agent -n 100 --no-pager
bash smoke-test.sh
sudo bash rotate-token.sh
```

## Advertencia

Este agente es deliberadamente poderoso: permite ejecucion remota de comandos y gestion de archivos. Usalo solo en entornos controlados o desechables, con HTTPS, token fuerte, firewall, snapshots y auditoria.
