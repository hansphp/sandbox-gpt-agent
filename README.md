# sandbox-gpt-rocky10

Servicio REST auditable para convertir un VPS Rocky Linux 10 en sandbox operable por un Custom GPT mediante GPT Actions.

El agente se instala como servicio `systemd`, reinicia automáticamente y expone una API protegida con Bearer token para ejecutar comandos y gestionar archivos.

## Contenido

- `agent.py`: servicio FastAPI.
- `install.sh`: instala el agente en Rocky Linux 10.
- `setup-nginx-https.sh`: publica el agente con Nginx + HTTPS + Certbot.
- `requirements.txt`: dependencias Python.
- `CUSTOM_GPT_INSTRUCTIONS.md`: instrucciones para el GPT Builder.
- `GUIA_COMPLETA_ROCKY10.md`: guía completa de instalación y uso.
- `smoke-test.sh`: prueba local.
- `rotate-token.sh`: rota el Bearer token.
- `uninstall.sh`: elimina el servicio.

## Instalación rápida

```bash
scp sandbox-gpt-rocky10.tar.gz root@IP_DEL_VPS:/tmp/
ssh root@IP_DEL_VPS
cd /tmp
tar xzf sandbox-gpt-rocky10.tar.gz
cd sandbox-gpt-rocky10
sudo bash install.sh
```

## Publicar para GPT Actions

Necesitas un dominio apuntando al VPS.

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

Este agente es deliberadamente poderoso: permite ejecución remota de comandos. Úsalo en un VPS controlado o desechable, con HTTPS, token fuerte, firewall y snapshots.
