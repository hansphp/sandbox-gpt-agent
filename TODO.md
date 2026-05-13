# TODO

Backlog para evolucionar `sandbox-gpt-agent` hacia un agente tecnologico de proposito general.

La meta no es limitarlo a IaC, despliegues o administracion de servidores. Debe poder resolver actividades tecnologicas autorizadas en distintos entornos de ejecucion: VPS, contenedores, servicios cloud, APIs externas, repositorios, navegadores, correo, mensajeria, datos, IA local, analisis de seguridad, automatizacion, diagnostico, pruebas, reportes y generacion de artefactos.

## Principios

- [ ] Disenar el agente como plataforma de capacidades.
  - Cada capacidad debe declarar permisos, secretos, red, archivos, comandos, riesgos y artefactos.
  - El core debe ser generico: ejecutar, auditar, proteger, organizar recursos y coordinar flujos.
  - Las habilidades concretas deben poder agregarse sin convertir el core en una mezcla de casos especiales.

- [ ] Separar claramente control, datos y evidencia.
  - Control: requests, politicas, aprobaciones, locks y sesiones.
  - Datos: workspace, inventario, secretos, modelos, datasets y recursos externos.
  - Evidencia: auditoria, artefactos, logs, capturas, reportes y checksums.

- [ ] Preferir defaults seguros con modo admin explicito.
  - Modo default: operar dentro del workspace, con secretos protegidos y acciones destructivas confirmadas.
  - Modo admin/root: opt-in, documentado, auditable y facil de desactivar.

## Prioridad alta

- [ ] Agregar bitacora forense de interacciones RAW en SQLite.
  - Crear `SANDBOX_INTERACTION_DB` con default en `/var/lib/sandbox-gpt-agent/interactions.db`.
  - Registrar por request: `request_id`, timestamp UTC, IP cliente confiable, metodo, path, query, `User-Agent` original, `User-Agent` normalizado, headers redactados, body RAW recibido, resultado de auth, status code, duracion, tamano de respuesta y error si aplica.
  - Capturar el payload exacto antes de parsearlo con Pydantic, incluyendo comandos, rutas, parametros y referencias a archivos cuando el tamano lo permita.
  - Guardar respuesta RAW o resumen/truncado configurable para reconstruir sesiones sin llenar disco.
  - Redactar `Authorization`, tokens bearer, cookies, URLs firmadas, passwords y patrones comunes de secretos antes de persistir.
  - Agregar limites por body/response, compresion opcional, retencion por dias/tamano y mantenimiento `VACUUM`.
  - Indexar timestamp, `request_id`, IP, endpoint, status code y `User-Agent` normalizado.
  - Exponer endpoints protegidos para consultar por `request_id`, rango de fechas, IP, endpoint, `User-Agent`, habilidad y evento.
  - Agregar hashes encadenados o checksums para detectar manipulacion accidental o maliciosa.

- [ ] Agregar `request_id`, idempotencia y locks.
  - Generar un UUID por request en middleware y devolverlo en `X-Request-ID`.
  - Permitir `X-Request-ID` externo solo si pasa validacion estricta.
  - Incluir `request_id` en audit log, interacciones, jobs, artefactos, shares, errores y respuestas JSON.
  - Agregar `operation_id` idempotente para evitar repetir acciones cuando ChatGPT o un cliente reintente.
  - Implementar locks por workspace, recurso, servidor, dominio, modelo, contenedor o ambiente para evitar operaciones concurrentes peligrosas.

- [ ] Definir arquitectura base de habilidades/capabilities.
  - Crear manifiestos por habilidad con nombre, descripcion, acciones, secretos requeridos, permisos de red, permisos de archivos y nivel de riesgo.
  - Declarar si cada accion es read-only, mutante, destructiva, publica datos o requiere confirmacion.
  - Permitir habilitar/deshabilitar habilidades por configuracion sin modificar codigo.
  - Registrar en auditoria que habilidad ejecuto cada accion y que permisos uso.
  - Crear pruebas contractuales para validar que una habilidad no accede a secretos, archivos o dominios fuera de su manifiesto.

- [ ] Agregar motor de politicas y aprobaciones.
  - Soportar reglas `allow`, `deny` y `require_confirmation` por habilidad, usuario, ambiente, recurso y tipo de accion.
  - Bloquear por defecto exposicion de llaves privadas, secretos, tokens y archivos sensibles.
  - Requerir aprobacion para borrados, publicacion de artefactos sensibles, comandos root, cambios DNS, `terraform apply/destroy` y acciones correctivas de seguridad.
  - Mantener una cola de aprobaciones con estados `pending`, `approved`, `rejected` y `expired`.
  - Auditar cada decision de politica con razon, `request_id`, habilidad y recurso afectado.

- [ ] Cambiar el modo seguro por defecto del instalador.
  - Crear un usuario dedicado `sandbox-gpt` en vez de correr el servicio como `root`.
  - Cambiar `SANDBOX_ALLOW_ABSOLUTE` a `0` por defecto.
  - Documentar modo `read_only`, `workspace`, `operator` y `admin`.
  - Mantener excepciones explicitas para escenarios donde se necesite control total del VPS.

- [ ] Corregir manejo de IP cliente en proxy.
  - Evitar confiar directamente en `X-Forwarded-For` enviado por el cliente.
  - Hacer que Nginx sobrescriba la IP con `$remote_addr` o usar `X-Real-IP` para rate limit y auditoria.
  - Persistir la IP normalizada en `request.state.client_ip` para que todos los endpoints, `audit.log` e `interactions.db` usen el mismo valor.

- [ ] Endurecer setup HTTPS con Certbot/Let's Encrypt.
  - Validar antes de ejecutar Certbot que `DOMAIN` resuelve a la IP publica del VPS.
  - Verificar que los puertos 80 y 443 esten accesibles y que `firewalld` permita `http` y `https`.
  - Comprobar que Nginx responde por HTTP antes de pedir el certificado.
  - Confirmar que la renovacion automatica de Certbot queda habilitada con systemd timer o cron.
  - Agregar comando de diagnostico para `certbot renew --dry-run`.
  - Ajustar headers de proxy para no confiar en `X-Forwarded-For` inyectado por el cliente.

- [ ] Marcar como consecuenciales las acciones mutantes en el schema OpenAPI.
  - Activar `x-openai-isConsequential: true` por defecto para comandos, jobs, archivos, shares, imports, acciones de habilidades y cualquier cambio externo.
  - Mantener como no consecuenciales las acciones de lectura: health, sys info, list/stat/read, jobs read-only, audit read-only e inventario read-only.

- [ ] Ajustar limites de respuesta para clientes tipo GPT Actions.
  - Mantener respuestas por debajo de 100,000 caracteres.
  - Coordinar `MAX_SYNC_OUTPUT_BYTES`, `MAX_READ_BYTES`, tails de jobs, artefactos y reportes.
  - Devolver metadata de truncado clara y recomendar lectura por chunks o descarga como artefacto.

- [ ] Agregar vault local de secretos.
  - Guardar tokens y credenciales cifrados o integrables con Vault/1Password/Bitwarden en el futuro.
  - Asignar secretos por scope de habilidad para evitar permisos compartidos innecesarios.
  - Redactar secretos automaticamente en requests, respuestas, stdout, stderr, audit log, `interactions.db` y artefactos.
  - Agregar comando para validar que no se filtren secretos en logs o archivos generados.

- [ ] Agregar gestion segura de llaves SSH.
  - Generar pares de llaves por proyecto, ambiente, usuario operativo o servidor.
  - Guardar la llave privada localmente con permisos `0600` y nunca devolverla por API ni incluirla en logs.
  - Exponer solo llave publica, fingerprint, ruta interna y metadata.
  - Agregar rotacion, revocacion y asociacion de llaves con servidores del inventario.

- [ ] Agregar inventario general de recursos.
  - Modelar servidores, dominios, zonas DNS, IPs, usuarios SSH, servicios, puertos, contenedores, bases de datos, modelos, datasets, jobs programados, artefactos y providers.
  - Asociar recursos con secretos, llaves, owner, ambiente, tags, TTL, fecha de alta, ultimo health check y notas operativas.
  - Exponer endpoints para listar, consultar, registrar, actualizar, desactivar y limpiar recursos.
  - Guardar estado en SQLite para empezar simple, dejando camino a backend externo despues.

- [ ] Crear registro formal de artefactos.
  - Registrar archivos generados con path, nombre, MIME type, tamano, hash SHA-256, job, request_id, habilidad origen y fecha.
  - Relacionar artefactos con URLs temporales de `shareFile`.
  - Exponer endpoints `listArtifacts`, `getArtifact`, `shareArtifact`, `deleteArtifact` y `exportArtifact`.
  - Soportar reportes, graficas, capturas, zips, dumps, datasets, modelos, planes IaC, logs y evidencias.

- [ ] Agregar lifecycle de workspace y laboratorios.
  - Implementar `resetWorkspace` con `dry_run`, confirmacion, snapshot previo y proteccion contra borrar fuera de `SANDBOX_WORKDIR`.
  - No tocar auditoria, secretos, llaves SSH, inventario ni configuracion del agente durante reset.
  - Agregar `createLab`, `statusLab`, `destroyLab` y `cleanupLab` con TTL, owner, recursos, artefactos y auditoria.
  - Registrar archivos, bytes y recursos eliminados con `request_id`, IP y `User-Agent`.

## Prioridad media

- [ ] Agregar motor de escenarios reproducibles.
  - Definir escenarios YAML/JSON con pasos, variables, dependencias, condiciones, reintentos y cleanup.
  - Soportar flujos no solo IaC: instalar software, ejecutar pruebas, generar datos, entrenar modelos, navegar sitios, consultar APIs, enviar reportes o limpiar recursos.
  - Guardar timeline, artefactos, logs, estado final y errores por paso.
  - Soportar `dry-run`, timeout por paso, aprobaciones y rollback cuando exista snapshot.

- [ ] Agregar gestor de software y servicios del entorno.
  - Instalar, actualizar, configurar y remover paquetes con `dnf`, `apt`, binarios descargados o scripts controlados.
  - Gestionar servicios `systemd`: status, start, stop, restart, enable, logs y health checks.
  - Registrar cambios de configuracion, backups previos y comandos ejecutados.
  - Requerir confirmacion para cambios globales del sistema.

- [ ] Agregar habilidad de IA local y workloads de modelos (`ai_lab`).
  - Instalar y gestionar runtimes como Ollama u otros motores locales cuando el entorno lo soporte.
  - Descargar, listar, ejecutar, detener y limpiar modelos con registro de tamano, origen, hash y requisitos.
  - Preparar datasets, prompts, evaluaciones y reportes para casos como deteccion de incidentes de seguridad.
  - Diferenciar entrenamiento, fine-tuning, RAG, evaluacion y clasificacion para no prometer capacidades equivocadas.
  - Medir CPU, RAM, disco, GPU si existe, latencia, throughput y consumo por job.
  - Guardar modelos, datasets, resultados, metricas y reportes como artefactos con retencion configurable.

- [ ] Agregar runner de IaC y configuracion.
  - Ejecutar Terraform/OpenTofu, Ansible y scripts de provisionamiento con working directories controlados.
  - Guardar planes, diffs, logs y salidas como artefactos.
  - Requerir confirmacion explicita para `apply`, `destroy` y playbooks destructivos.
  - Asociar ejecuciones con inventario, ambiente, request_id, commit o version de modulo.
  - Redactar variables sensibles antes de auditar o devolver respuestas.

- [ ] Agregar executor SSH remoto.
  - Ejecutar comandos en servidores del inventario usando llaves administradas por el agente.
  - Registrar host, usuario, llave, ambiente, comando, salida truncada, artefactos y exit code.
  - Bloquear comandos destructivos o root sin politica/aprobacion.
  - Soportar transferencia segura de archivos y recoleccion de logs.

- [ ] Agregar habilidades de proveedores externos.
  - Cloudflare DNS: zonas, records, subdominios temporales, propagacion, cleanup por tag/prefijo y tokens de minimo privilegio.
  - Providers de computo/cloud: crear, listar, etiquetar, apagar y destruir servidores, instancias o recursos temporales con TTL y confirmacion para destruccion.
  - Object storage: subir/bajar artefactos, backups, datasets y exports de auditoria.
  - Mantener providers como habilidades desacopladas con manifiestos y scopes de secretos.

- [ ] Agregar habilidad de notificaciones Telegram.
  - Configurar bot token y allowlist de `chat_id`.
  - Enviar mensajes, imagenes, documentos, reportes, logs y artefactos.
  - Impedir envio a chats no autorizados.
  - Auditar destinatario, artefacto enviado, tamano y resultado de envio sin exponer tokens.

- [ ] Agregar habilidad de correo electronico controlado.
  - Configurar una cuenta dedicada y preferir OAuth o app password en vez de password normal.
  - Leer correo en modo read-only por defecto con filtros por remitente, asunto, etiqueta y fecha.
  - Descargar adjuntos como artefactos con redaccion y limites de tamano.
  - Auditar acceso a mensajes sin guardar contenido sensible completo salvo modo forense explicito.

- [ ] Agregar habilidad de navegador con Playwright.
  - Capturar screenshots, PDFs, consola, errores JS y trazas de red.
  - Guardar capturas como artefactos y opcionalmente enviarlas por Telegram.
  - Soportar perfiles aislados por escenario para pruebas de login y flujos web.
  - Agregar limites de tiempo, dominios permitidos y limpieza de perfiles temporales.

- [ ] Agregar habilidad de observabilidad y diagnostico.
  - Revisar estado de servicios `systemd`, logs de `journalctl`, CPU, RAM, disco, procesos y puertos.
  - Validar DNS, TLS, HTTP, redirects, certificados, Nginx, FastAPI, Docker/Podman, SSH y runtimes de IA.
  - Generar reportes Markdown/HTML/PDF con hallazgos, evidencias y recomendaciones.
  - Guardar reportes como artefactos y opcionalmente enviarlos por Telegram.

- [ ] Agregar habilidad de pruebas de red (`network_probe`).
  - Ejecutar DNS lookup, ping, traceroute, pruebas de puertos, TLS handshake y HTTP status/headers.
  - Medir latencia y detectar errores de resolucion, firewall, certificados o redirects.
  - Restringir probes a dominios/IPs del inventario o allowlist para evitar escaneos no autorizados.
  - Guardar resultados como artefactos trazables por request_id y ambiente.

- [ ] Agregar habilidad de laboratorios con contenedores (`container_lab`).
  - Crear entornos temporales con Docker/Podman Compose.
  - Levantar stacks multi-servicio para pruebas: app, base de datos, cache, proxy, workers, colas, APIs y runtimes IA.
  - Asociar labs con TTL, owner, puertos, logs y artefactos generados.
  - Implementar cleanup automatico de redes, volumenes y contenedores temporales.

- [ ] Agregar habilidad GitOps (`gitops_runner`).
  - Clonar repositorios autorizados, crear ramas, aplicar cambios, correr tests y generar diffs.
  - Soportar GitHub/GitLab en modo opcional para abrir PRs o issues con confirmacion explicita.
  - Guardar patches, resultados de tests y logs como artefactos.
  - Redactar tokens y limitar acceso por repos allowlist.

- [ ] Agregar habilidad de laboratorios de base de datos (`database_lab`).
  - Crear bases temporales Postgres, MySQL/MariaDB, Redis u otros motores requeridos por escenarios.
  - Ejecutar migraciones, seed data, backups, restores y pruebas de conectividad.
  - Guardar dumps, logs y resultados como artefactos con limites de tamano.
  - Aislar credenciales por ambiente y destruir recursos temporales por TTL.

- [ ] Agregar habilidad de baseline de seguridad (`security_baseline`).
  - Revisar firewall, SSH, usuarios, permisos, puertos expuestos, headers HTTP, configuraciones debiles y dependencias vulnerables.
  - Operar en modo read-only por defecto y limitarse al inventario autorizado.
  - Generar reporte con severidad, evidencia, impacto y recomendacion.
  - Requerir confirmacion para cualquier accion correctiva.

- [ ] Agregar habilidad de backups y snapshots.
  - Respaldar archivos de configuracion, carpetas criticas, bases de datos, datasets, modelos o estados IaC antes de cambios riesgosos.
  - Guardar hashes, metadata, origen, destino, request_id y politica de retencion.
  - Permitir rollback controlado con confirmacion explicita.
  - Integrar snapshots con artefactos, auditoria y motor de politicas.

- [ ] Agregar habilidad de limpieza de recursos temporales (`cleanup_janitor`).
  - Eliminar jobs antiguos, artefactos vencidos, enlaces `shareFile` expirados, contenedores detenidos, modelos temporales, datasets temporales y labs con TTL cumplido.
  - Limpiar registros DNS temporales por tag/prefijo y recursos de inventario marcados como desactivados.
  - Ejecutarse manualmente o de forma programada con modo `dry-run`.
  - Auditar cada recurso eliminado y permitir reporte previo antes de borrar.

- [ ] Agregar generador de reportes (`report_builder`).
  - Convertir logs, capturas, resultados de pruebas, planes IaC, diagnosticos, evaluaciones de modelos y evidencias en reportes Markdown, HTML o PDF.
  - Incluir resumen ejecutivo, pasos ejecutados, evidencias, artefactos, metricas y errores.
  - Compartir reportes mediante `shareFile`, Telegram u object storage.
  - Usar plantillas versionadas por tipo de escenario.

- [ ] Agregar programador y disparadores.
  - Ejecutar escenarios, diagnosticos, backups, limpiezas o reportes por cron/systemd timer.
  - Soportar webhooks protegidos para disparar flujos desde herramientas externas.
  - Registrar cada ejecucion programada con `request_id`, politica aplicada y artefactos generados.

- [ ] Agregar proteccion anti-SSRF en descargas y fetches.
  - Bloquear `localhost`, rangos privados, link-local y metadata cloud salvo allowlist explicita.
  - Revalidar redirects y DNS rebinding.
  - Permitir override explicito por variable de entorno solo para laboratorios controlados.

- [ ] Limitar operaciones de archivos grandes y listados.
  - Agregar limite de tamano a `rawUpload`.
  - Agregar paginacion o limite maximo a `listFiles`.
  - Revisar `writeFile`, imports, exports, datasets, modelos y artefactos para evitar payloads excesivos.

- [ ] Endurecer `shareFile`.
  - Evitar compartir archivos fuera del workspace cuando `SANDBOX_ALLOW_ABSOLUTE=0`.
  - Agregar opcion de revocar enlaces activos y listar shares vigentes.
  - Auditar descargas con IP, `User-Agent`, artefacto y contexto sin exponer tokens completos.

- [ ] Agregar modo de auditoria configurable.
  - `SANDBOX_AUDIT_MODE=summary|full|off`, con `summary` como default seguro.
  - En `full`, guardar body/response RAW con limites estrictos para sesiones de diagnostico.
  - En `summary`, guardar metadata, hashes SHA-256 de payloads y campos redaccionados.
  - Documentar riesgos de privacidad: comandos, rutas, prompts, correo, datasets y contenido de archivos pueden quedar persistidos.

- [ ] Crear endpoints de exportacion de auditoria.
  - Exportar eventos como JSONL o CSV por rango de fechas y filtros.
  - Incluir checksums para preservar evidencia de auditoria.
  - Requerir confirmacion explicita o flag consecuencial para exportar payloads RAW.
  - Permitir export externo a object storage, syslog remoto o webhook seguro.

## Prioridad baja

- [ ] Agregar panel CLI de diagnostico.
  - Comando `sandbox doctor` para revisar dependencias, permisos, Nginx, Certbot, firewalld, disco, DB, logs, token, Playwright, Docker/Podman, runtimes IA y conectividad.
  - Comando para ver ultimas interacciones, errores por endpoint, IPs frecuentes, User-Agents, recursos activos y comandos recientes.
  - Comando para purgar auditoria antigua respetando retencion.

- [ ] Agregar suite de tests.
  - Auth requerida y token invalido.
  - Path traversal y paths absolutos desactivados.
  - Truncado de stdout/stderr/readFile.
  - Jobs background, kill, locks e idempotencia.
  - Import/export de archivos.
  - Shares con expiracion, revocacion y max downloads.
  - Auditoria SQLite: captura RAW, redaccion de secretos, limites de tamano, User-Agent y busqueda por `request_id`.
  - Politicas: allow, deny, confirmaciones y bloqueo de secretos.
  - Habilidades: contrato de manifiesto, permisos y scopes de secretos.

- [ ] Endurecer `systemd`.
  - Evaluar `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`, `ReadWritePaths`, `LimitNPROC` y limites de memoria.
  - Mantener excepciones documentadas para el modo root/admin.
  - Definir perfiles segun modo `read_only`, `workspace`, `operator` y `admin`.

- [ ] Limpiar jobs antiguos.
  - Agregar TTL configurable para directorios en `STATE_DIR/jobs`.
  - Crear comando o endpoint administrativo para cleanup.
  - Integrar limpieza con artefactos, auditoria y `cleanup_janitor`.

- [ ] Evitar drift entre schemas.
  - Generar `openapi-actions-template.yaml` desde `render_gpt_schema()`, o eliminar el template estatico.
  - Agregar una prueba que compare endpoints reales contra el schema publicado.
  - Mantener descripciones cortas para no exceder limites de GPT Actions.

- [ ] Mejorar schemas de respuesta OpenAPI.
  - Definir modelos de respuesta para exec, jobs, archivos, shares, artefactos, inventario, habilidades, auditoria y errores.
  - Estandarizar `ok`, `request_id`, `operation_id`, `warnings`, `truncated`, `artifacts` y `next_steps`.

- [ ] Ampliar smoke tests.
  - Probar health, auth, exec, write/read, background job, share, audit, artifacts y resetWorkspace dry-run.
  - Soportar ejecucion contra host local y host HTTPS publicado.
  - Agregar prueba opcional para Nginx, Certbot, firewalld y renovacion dry-run.

- [ ] Agregar documentacion por escenarios.
  - Ejemplos para administracion basica de entornos, diagnostico, generacion de reportes, Cloudflare DNS, Telegram, Playwright, contenedores, bases de datos, IaC e IA local con Ollama.
  - Incluir recomendaciones de seguridad, scopes de tokens, retencion de auditoria y cleanup.
