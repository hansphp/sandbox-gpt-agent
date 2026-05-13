# TODO

Backlog de mejoras recomendadas para endurecer y evolucionar `sandbox-gpt-agent`.

## Prioridad alta

- [ ] Cambiar el modo seguro por defecto del instalador.
  - Crear un usuario dedicado `sandbox-gpt` en vez de correr el servicio como `root`.
  - Cambiar `SANDBOX_ALLOW_ABSOLUTE` a `0` por defecto.
  - Documentar un modo admin/root explicito para casos donde se necesite control total del VPS.

- [ ] Marcar como consecuenciales las acciones mutantes en el schema OpenAPI.
  - Activar `x-openai-isConsequential: true` por defecto para `runCommand`, `killJob`, `writeFile`, `makeDirectory`, `chmodFile`, `fetchUrlToFile`, `deleteFile`, `importOpenAIConversationFiles` y `shareFile`.
  - Mantener como no consecuenciales las acciones de lectura: health, sys info, list/stat/read, jobs, audit y export.

- [ ] Ajustar limites de respuesta para GPT Actions.
  - Mantener respuestas por debajo de 100,000 caracteres.
  - Reducir o coordinar `MAX_SYNC_OUTPUT_BYTES`, `MAX_READ_BYTES` y tails de jobs.
  - Devolver metadata de truncado clara y recomendar lectura por chunks.

- [ ] Corregir manejo de IP cliente en proxy.
  - Evitar confiar directamente en `X-Forwarded-For` enviado por el cliente.
  - Hacer que Nginx sobrescriba la IP con `$remote_addr` o usar `X-Real-IP` para rate limit y auditoria.

## Prioridad media

- [ ] Agregar proteccion anti-SSRF en `fetchUrlToFile`.
  - Bloquear `localhost`, rangos privados, link-local y metadata cloud.
  - Revalidar redirects.
  - Permitir override explicito por variable de entorno solo para laboratorios controlados.

- [ ] Limitar operaciones de archivos grandes y listados.
  - Agregar limite de tamano a `rawUpload`.
  - Agregar paginacion o limite maximo a `listFiles`.
  - Revisar `writeFile` para evitar payloads excesivos.

- [ ] Endurecer `shareFile`.
  - Evitar compartir archivos fuera del workspace cuando `SANDBOX_ALLOW_ABSOLUTE=0`.
  - Agregar opcion de revocar enlaces activos.
  - Auditar descargas con mas contexto util sin exponer tokens completos.

- [ ] Agregar rotacion y redaccion de logs.
  - Configurar `logrotate` para `/var/log/sandbox-gpt-agent/audit.log`.
  - Redactar tokens, headers sensibles, URLs firmadas y secretos comunes antes de auditar.

- [ ] Evitar drift entre schemas.
  - Generar `openapi-actions-template.yaml` desde `render_gpt_schema()`, o eliminar el template estatico.
  - Agregar una prueba que compare endpoints reales contra el schema publicado.

## Prioridad baja

- [ ] Agregar suite de tests.
  - Auth requerida y token invalido.
  - Path traversal y paths absolutos desactivados.
  - Truncado de stdout/stderr/readFile.
  - Jobs background y kill.
  - Import/export de archivos.
  - Shares con expiracion y max downloads.

- [ ] Endurecer `systemd`.
  - Evaluar `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`, `ReadWritePaths`, `LimitNPROC` y limites de memoria.
  - Mantener excepciones documentadas para el modo root/admin.

- [ ] Limpiar jobs antiguos.
  - Agregar TTL configurable para directorios en `STATE_DIR/jobs`.
  - Crear comando o endpoint administrativo para cleanup.

- [ ] Mejorar schemas de respuesta OpenAPI.
  - Definir modelos de respuesta para exec, jobs, archivos, shares y errores.
  - Mantener descripciones cortas para no exceder limites de GPT Actions.

- [ ] Ampliar smoke tests.
  - Probar health, auth, exec, write/read, background job, share y audit.
  - Soportar ejecucion contra host local y host HTTPS publicado.

