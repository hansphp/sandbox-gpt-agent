# TODO

Backlog para evolucionar `sandbox-gpt-agent` hacia un agente tecnológico de propósito general.

La meta no es limitarlo a IaC, despliegues o administración de servidores. Debe poder resolver actividades tecnológicas autorizadas en distintos entornos de ejecución: VPS, contenedores, servicios en la nube, APIs externas, repositorios, navegadores, correo, mensajería, datos, IA local, análisis de seguridad, automatización, diagnóstico, pruebas, reportes y generación de artefactos.

## Principios

- [ ] Diseñar el agente como plataforma de capacidades.
  - Cada capacidad debe declarar permisos, secretos, red, archivos, comandos, riesgos y artefactos.
  - El núcleo debe ser genérico: ejecutar, auditar, proteger, organizar recursos y coordinar flujos.
  - Las habilidades concretas deben poder agregarse sin convertir el núcleo en una mezcla de casos especiales.

- [ ] Separar claramente control, datos y evidencia.
  - Control: solicitudes, políticas, aprobaciones, bloqueos y sesiones.
  - Datos: workspace, inventario, secretos, modelos, datasets y recursos externos.
  - Evidencia: auditoría, artefactos, logs, capturas, reportes y checksums.

- [ ] Preferir valores predeterminados seguros con modo admin explícito.
  - Modo predeterminado: operar dentro del workspace, con secretos protegidos y acciones destructivas confirmadas.
  - Modo admin/root: opt-in, documentado, auditable y fácil de desactivar.

## Prioridad alta

- [ ] Agregar bitácora forense de interacciones RAW en SQLite.
  - Crear `SANDBOX_INTERACTION_DB` con valor predeterminado en `/var/lib/sandbox-gpt-agent/interactions.db`.
  - Registrar por solicitud: `request_id`, timestamp UTC, IP confiable del cliente, método, path, query, `User-Agent` original, `User-Agent` normalizado, encabezados redactados, cuerpo RAW recibido, resultado de autenticación, código de estado, duración, tamaño de respuesta y error si aplica.
  - Capturar el payload exacto antes de parsearlo con Pydantic, incluyendo comandos, rutas, parámetros y referencias a archivos cuando el tamaño lo permita.
  - Guardar respuesta RAW o resumen/truncado configurable para reconstruir sesiones sin llenar disco.
  - Redactar `Authorization`, tokens bearer, cookies, URLs firmadas, passwords y patrones comunes de secretos antes de persistir.
  - Agregar límites por body/response, compresión opcional, retención por días/tamaño y mantenimiento `VACUUM`.
  - Indexar timestamp, `request_id`, IP, endpoint, código de estado y `User-Agent` normalizado.
  - Exponer endpoints protegidos para consultar por `request_id`, rango de fechas, IP, endpoint, `User-Agent`, habilidad y evento.
  - Agregar hashes encadenados o checksums para detectar manipulación accidental o maliciosa.

- [ ] Agregar `request_id`, idempotencia y locks.
  - Generar un UUID por solicitud en middleware y devolverlo en `X-Request-ID`.
  - Permitir `X-Request-ID` externo solo si pasa una validación estricta.
  - Incluir `request_id` en audit log, interacciones, jobs, artefactos, shares, errores y respuestas JSON.
  - Agregar `operation_id` idempotente para evitar repetir acciones cuando ChatGPT o un cliente reintente.
  - Implementar locks por workspace, recurso, servidor, dominio, modelo, contenedor o ambiente para evitar operaciones concurrentes peligrosas.

- [ ] Definir la arquitectura base de habilidades/capabilities.
  - Crear manifiestos por habilidad con nombre, descripción, acciones, secretos requeridos, permisos de red, permisos de archivos y nivel de riesgo.
  - Declarar si cada acción es read-only, mutante, destructiva, publica datos o requiere confirmación.
  - Permitir habilitar/deshabilitar habilidades mediante configuración, sin modificar código.
  - Registrar en auditoría qué habilidad ejecutó cada acción y qué permisos utilizó.
  - Crear pruebas contractuales para validar que una habilidad no accede a secretos, archivos o dominios fuera de su manifiesto.

- [ ] Agregar un motor de políticas y aprobaciones.
  - Soportar reglas `allow`, `deny` y `require_confirmation` por habilidad, usuario, ambiente, recurso y tipo de acción.
  - Bloquear por defecto exposición de llaves privadas, secretos, tokens y archivos sensibles.
  - Requerir aprobación para borrados, publicación de artefactos sensibles, comandos root, cambios DNS, `terraform apply/destroy` y acciones correctivas de seguridad.
  - Mantener una cola de aprobaciones con estados `pending`, `approved`, `rejected` y `expired`.
  - Auditar cada decisión de política con razón, `request_id`, habilidad y recurso afectado.

- [ ] Cambiar el modo seguro predeterminado del instalador.
  - Crear un usuario dedicado `sandbox-gpt` en vez de correr el servicio como `root`.
  - Cambiar `SANDBOX_ALLOW_ABSOLUTE` a `0` por defecto.
  - Documentar modo `read_only`, `workspace`, `operator` y `admin`.
  - Mantener excepciones explícitas para escenarios donde se necesite control total del VPS.

- [ ] Corregir el manejo de la IP del cliente en el proxy.
  - Evitar confiar directamente en `X-Forwarded-For` enviado por el cliente.
  - Hacer que Nginx sobrescriba la IP con `$remote_addr` o usar `X-Real-IP` para limitación de tasa y auditoría.
  - Persistir la IP normalizada en `request.state.client_ip` para que todos los endpoints, `audit.log` e `interactions.db` usen el mismo valor.

- [ ] Endurecer la configuración HTTPS con Certbot/Let's Encrypt.
  - Validar antes de ejecutar Certbot que `DOMAIN` resuelve a la IP pública del VPS.
  - Verificar que los puertos 80 y 443 estén accesibles y que `firewalld` permita `http` y `https`.
  - Comprobar que Nginx responde por HTTP antes de pedir el certificado.
  - Confirmar que la renovación automática de Certbot queda habilitada con systemd timer o cron.
  - Agregar comando de diagnóstico para `certbot renew --dry-run`.
  - Ajustar los encabezados de proxy para no confiar en `X-Forwarded-For` inyectado por el cliente.

- [ ] Marcar como consecuenciales las acciones mutantes en el esquema OpenAPI.
  - Activar `x-openai-isConsequential: true` por defecto para comandos, jobs, archivos, shares, imports, acciones de habilidades y cualquier cambio externo.
  - Mantener como no consecuenciales las acciones de lectura: health, sys info, list/stat/read, jobs read-only, audit read-only e inventario read-only.

- [ ] Ajustar los límites de respuesta para clientes tipo GPT Actions.
  - Mantener respuestas por debajo de 100,000 caracteres.
  - Coordinar `MAX_SYNC_OUTPUT_BYTES`, `MAX_READ_BYTES`, tails de jobs, artefactos y reportes.
  - Devolver metadatos de truncado claros y recomendar lectura por fragmentos o descarga como artefacto.

- [ ] Agregar una bóveda local de secretos.
  - Guardar tokens y credenciales cifrados o integrables con Vault/1Password/Bitwarden en el futuro.
  - Asignar secretos por alcance de habilidad para evitar permisos compartidos innecesarios.
  - Redactar secretos automáticamente en solicitudes, respuestas, stdout, stderr, audit log, `interactions.db` y artefactos.
  - Agregar comando para validar que no se filtren secretos en logs o archivos generados.

- [ ] Agregar gestión segura de llaves SSH.
  - Generar pares de llaves por proyecto, ambiente, usuario operativo o servidor.
  - Guardar la llave privada localmente con permisos `0600` y nunca devolverla por API ni incluirla en logs.
  - Exponer solo la llave pública, la huella digital, la ruta interna y los metadatos.
  - Agregar rotación, revocación y asociación de llaves con servidores del inventario.

- [ ] Agregar un inventario general de recursos.
  - Modelar servidores, dominios, zonas DNS, IPs, usuarios SSH, servicios, puertos, contenedores, bases de datos, modelos, datasets, jobs programados, artefactos y proveedores.
  - Asociar recursos con secretos, llaves, responsable, ambiente, etiquetas, TTL, fecha de alta, última comprobación de salud y notas operativas.
  - Exponer endpoints para listar, consultar, registrar, actualizar, desactivar y limpiar recursos.
  - Guardar estado en SQLite para empezar de forma simple y dejar abierta la posibilidad de migrar a un backend externo después.

- [ ] Crear un registro formal de artefactos.
  - Registrar archivos generados con path, nombre, tipo MIME, tamaño, hash SHA-256, job, request_id, habilidad de origen y fecha.
  - Relacionar artefactos con URLs temporales de `shareFile`.
  - Exponer endpoints `listArtifacts`, `getArtifact`, `shareArtifact`, `deleteArtifact` y `exportArtifact`.
  - Soportar reportes, gráficas, capturas, archivos ZIP, dumps, datasets, modelos, planes IaC, logs y evidencias.

- [ ] Agregar ciclo de vida de workspace y laboratorios.
  - Implementar `resetWorkspace` con `dry_run`, confirmación, snapshot previo y protección contra borrar fuera de `SANDBOX_WORKDIR`.
  - No modificar auditoría, secretos, llaves SSH, inventario ni configuración del agente durante el reset.
  - Agregar `createLab`, `statusLab`, `destroyLab` y `cleanupLab` con TTL, responsable, recursos, artefactos y auditoría.
  - Registrar archivos, bytes y recursos eliminados con `request_id`, IP y `User-Agent`.

## Prioridad media

- [ ] Agregar un motor de escenarios reproducibles.
  - Definir escenarios YAML/JSON con pasos, variables, dependencias, condiciones, reintentos y limpieza.
  - Soportar flujos no solo IaC: instalar software, ejecutar pruebas, generar datos, entrenar modelos, navegar sitios, consultar APIs, enviar reportes o limpiar recursos.
  - Guardar línea de tiempo, artefactos, logs, estado final y errores por paso.
  - Soportar `dry-run`, tiempo de espera por paso, aprobaciones y reversión cuando exista snapshot.

- [ ] Agregar un gestor de software y servicios del entorno.
  - Instalar, actualizar, configurar y eliminar paquetes con `dnf`, `apt`, binarios descargados o scripts controlados.
  - Gestionar servicios `systemd`: status, start, stop, restart, enable, logs y comprobaciones de salud.
  - Registrar cambios de configuración, respaldos previos y comandos ejecutados.
  - Requerir confirmación para cambios globales del sistema.

- [ ] Agregar habilidad de IA local y cargas de trabajo de modelos (`ai_lab`).
  - Instalar y gestionar runtimes como Ollama u otros motores locales cuando el entorno lo soporte.
  - Descargar, listar, ejecutar, detener y limpiar modelos, con registro de tamaño, origen, hash y requisitos.
  - Preparar datasets, prompts, evaluaciones y reportes para casos como detección de incidentes de seguridad.
  - Diferenciar entrenamiento, fine-tuning, RAG, evaluación y clasificación para no prometer capacidades incorrectas.
  - Medir CPU, RAM, disco, GPU si existe, latencia, throughput y consumo por job.
  - Guardar modelos, datasets, resultados, métricas y reportes como artefactos con retención configurable.

- [ ] Agregar ejecutor de IaC y configuración.
  - Ejecutar Terraform/OpenTofu, Ansible y scripts de aprovisionamiento con directorios de trabajo controlados.
  - Guardar planes, diferencias, logs y salidas como artefactos.
  - Requerir confirmación explícita para `apply`, `destroy` y playbooks destructivos.
  - Asociar ejecuciones con inventario, ambiente, request_id, commit o versión de módulo.
  - Redactar variables sensibles antes de auditar o devolver respuestas.

- [ ] Agregar un ejecutor SSH remoto.
  - Ejecutar comandos en servidores del inventario usando llaves administradas por el agente.
  - Registrar host, usuario, llave, ambiente, comando, salida truncada, artefactos y código de salida.
  - Bloquear comandos destructivos o root sin política/aprobación.
  - Soportar transferencia segura de archivos y recolección de logs.

- [ ] Agregar habilidades de proveedores externos.
  - Cloudflare DNS: zonas, registros, subdominios temporales, propagación, limpieza por etiqueta/prefijo y tokens de mínimo privilegio.
  - Proveedores de cómputo/cloud: crear, listar, etiquetar, apagar y destruir servidores, instancias o recursos temporales con TTL y confirmación para destrucción.
  - Almacenamiento de objetos: subir/bajar artefactos, respaldos, datasets y exportaciones de auditoría.
  - Mantener proveedores como habilidades desacopladas con manifiestos y alcances de secretos.

- [ ] Agregar habilidad de notificaciones Telegram.
  - Configurar bot token y lista de permitidos de `chat_id`.
  - Enviar mensajes, imágenes, documentos, reportes, logs y artefactos.
  - Impedir envíos a chats no autorizados.
  - Auditar destinatario, artefacto enviado, tamaño y resultado de envío sin exponer tokens.

- [ ] Agregar habilidad de correo electrónico controlado.
  - Configurar una cuenta dedicada y preferir OAuth o contraseña de aplicación en vez de contraseña normal.
  - Leer correo en modo read-only por defecto con filtros por remitente, asunto, etiqueta y fecha.
  - Descargar adjuntos como artefactos, con redacción y límites de tamaño.
  - Auditar acceso a mensajes sin guardar contenido sensible completo salvo modo forense explícito.

- [ ] Agregar habilidad de navegador con Playwright.
  - Capturar pantallas, PDFs, consola, errores JS y trazas de red.
  - Guardar capturas como artefactos y opcionalmente enviarlas por Telegram.
  - Soportar perfiles aislados por escenario para pruebas de login y flujos web.
  - Agregar límites de tiempo, dominios permitidos y limpieza de perfiles temporales.

- [ ] Agregar habilidad de observabilidad y diagnóstico.
  - Revisar estado de servicios `systemd`, logs de `journalctl`, CPU, RAM, disco, procesos y puertos.
  - Validar DNS, TLS, HTTP, redirects, certificados, Nginx, FastAPI, Docker/Podman, SSH y runtimes de IA.
  - Generar reportes Markdown/HTML/PDF con hallazgos, evidencias y recomendaciones.
  - Guardar reportes como artefactos y opcionalmente enviarlos por Telegram.

- [ ] Agregar habilidad de pruebas de red (`network_probe`).
  - Ejecutar DNS lookup, ping, traceroute, pruebas de puertos, TLS handshake y estado/encabezados HTTP.
  - Medir latencia y detectar errores de resolución, firewall, certificados o redirects.
  - Restringir probes a dominios/IPs del inventario o a una lista de permitidos para evitar escaneos no autorizados.
  - Guardar resultados como artefactos trazables por request_id y ambiente.

- [ ] Agregar habilidad de laboratorios con contenedores (`container_lab`).
  - Crear entornos temporales con Docker/Podman Compose.
  - Levantar stacks multiservicio para pruebas: app, base de datos, caché, proxy, workers, colas, APIs y runtimes de IA.
  - Asociar labs con TTL, responsable, puertos, logs y artefactos generados.
  - Implementar limpieza automática de redes, volúmenes y contenedores temporales.

- [ ] Agregar habilidad GitOps (`gitops_runner`).
  - Clonar repositorios autorizados, crear ramas, aplicar cambios, correr pruebas y generar diferencias.
  - Soportar GitHub/GitLab en modo opcional para abrir PRs o issues con confirmación explícita.
  - Guardar parches, resultados de pruebas y logs como artefactos.
  - Redactar tokens y limitar el acceso por repositorios permitidos.

- [ ] Agregar habilidad de laboratorios de base de datos (`database_lab`).
  - Crear bases temporales en Postgres, MySQL/MariaDB, Redis u otros motores requeridos por los escenarios.
  - Ejecutar migraciones, datos semilla, respaldos, restauraciones y pruebas de conectividad.
  - Guardar dumps, logs y resultados como artefactos, con límites de tamaño.
  - Aislar credenciales por ambiente y destruir recursos temporales por TTL.

- [ ] Agregar habilidad de línea base de seguridad (`security_baseline`).
  - Revisar firewall, SSH, usuarios, permisos, puertos expuestos, encabezados HTTP, configuraciones débiles y dependencias vulnerables.
  - Operar en modo read-only de forma predeterminada y limitarse al inventario autorizado.
  - Generar reporte con severidad, evidencia, impacto y recomendación.
  - Requerir confirmación para cualquier acción correctiva.

- [ ] Agregar habilidad de respaldos y snapshots.
  - Respaldar archivos de configuración, carpetas críticas, bases de datos, datasets, modelos o estados IaC antes de cambios riesgosos.
  - Guardar hashes, metadatos, origen, destino, request_id y política de retención.
  - Permitir rollback controlado con confirmación explícita.
  - Integrar snapshots con artefactos, auditoría y motor de políticas.

- [ ] Agregar habilidad de limpieza de recursos temporales (`cleanup_janitor`).
  - Eliminar jobs antiguos, artefactos vencidos, enlaces `shareFile` expirados, contenedores detenidos, modelos temporales, datasets temporales y labs con TTL cumplido.
  - Limpiar registros DNS temporales por tag/prefijo y recursos de inventario marcados como desactivados.
  - Ejecutarse manualmente o de forma programada con modo `dry-run`.
  - Auditar cada recurso eliminado y permitir reporte previo antes de borrar.

- [ ] Agregar un generador de reportes (`report_builder`).
  - Convertir logs, capturas, resultados de pruebas, planes IaC, diagnósticos, evaluaciones de modelos y evidencias en reportes Markdown, HTML o PDF.
  - Incluir resumen ejecutivo, pasos ejecutados, evidencias, artefactos, métricas y errores.
  - Compartir reportes mediante `shareFile`, Telegram o almacenamiento de objetos.
  - Usar plantillas versionadas por tipo de escenario.

- [ ] Agregar un programador y disparadores.
  - Ejecutar escenarios, diagnósticos, respaldos, limpiezas o reportes por cron/systemd timer.
  - Soportar webhooks protegidos para disparar flujos desde herramientas externas.
  - Registrar cada ejecución programada con `request_id`, política aplicada y artefactos generados.

- [ ] Agregar protección anti-SSRF en descargas y fetches.
  - Bloquear `localhost`, rangos privados, link-local y servicios de metadatos cloud, salvo lista de permitidos explícita.
  - Revalidar redirects y DNS rebinding.
  - Permitir sobrescritura explícita por variable de entorno solo para laboratorios controlados.

- [ ] Limitar operaciones de archivos grandes y listados.
  - Agregar límite de tamaño a `rawUpload`.
  - Agregar paginación o límite máximo a `listFiles`.
  - Revisar `writeFile`, imports, exports, datasets, modelos y artefactos para evitar payloads excesivos.

- [ ] Endurecer `shareFile`.
  - Evitar compartir archivos fuera del workspace cuando `SANDBOX_ALLOW_ABSOLUTE=0`.
  - Agregar opción de revocar enlaces activos y listar shares vigentes.
  - Auditar descargas con IP, `User-Agent`, artefacto y contexto sin exponer tokens completos.

- [ ] Agregar un modo de auditoría configurable.
  - `SANDBOX_AUDIT_MODE=summary|full|off`, con `summary` como valor predeterminado seguro.
  - En `full`, guardar body/response RAW con límites estrictos para sesiones de diagnóstico.
  - En `summary`, guardar metadatos, hashes SHA-256 de payloads y campos redactados.
  - Documentar riesgos de privacidad: comandos, rutas, prompts, correo, datasets y contenido de archivos pueden quedar persistidos.

- [ ] Crear endpoints de exportación de auditoría.
  - Exportar eventos como JSONL o CSV por rango de fechas y filtros.
  - Incluir checksums para preservar evidencia de auditoría.
  - Requerir confirmación explícita o marca consecuencial para exportar payloads RAW.
  - Permitir exportación externa a almacenamiento de objetos, syslog remoto o webhook seguro.

## Prioridad baja

- [ ] Agregar un panel CLI de diagnóstico.
  - Comando `sandbox doctor` para revisar dependencias, permisos, Nginx, Certbot, firewalld, disco, base de datos, logs, token, Playwright, Docker/Podman, runtimes IA y conectividad.
  - Comando para ver las últimas interacciones, errores por endpoint, IPs frecuentes, User-Agents, recursos activos y comandos recientes.
  - Comando para purgar auditoría antigua respetando la retención.

- [ ] Agregar una suite de pruebas.
  - Autenticación requerida y token inválido.
  - Path traversal y paths absolutos desactivados.
  - Truncado de stdout/stderr/readFile.
  - Jobs background, kill, locks e idempotencia.
  - Importación/exportación de archivos.
  - Shares con expiración, revocación y max downloads.
  - Auditoría SQLite: captura RAW, redacción de secretos, límites de tamaño, User-Agent y búsqueda por `request_id`.
  - Políticas: allow, deny, confirmaciones y bloqueo de secretos.
  - Habilidades: contrato de manifiesto, permisos y alcances de secretos.

- [ ] Endurecer `systemd`.
  - Evaluar `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem`, `ReadWritePaths`, `LimitNPROC` y límites de memoria.
  - Mantener excepciones documentadas para el modo root/admin.
  - Definir perfiles según modo `read_only`, `workspace`, `operator` y `admin`.

- [ ] Limpiar jobs antiguos.
  - Agregar TTL configurable para directorios en `STATE_DIR/jobs`.
  - Crear comando o endpoint administrativo para limpieza.
  - Integrar limpieza con artefactos, auditoría y `cleanup_janitor`.

- [ ] Evitar desviaciones entre esquemas.
  - Generar `openapi-actions-template.yaml` desde `render_gpt_schema()`, o eliminar el template estático.
  - Agregar una prueba que compare endpoints reales contra el esquema publicado.
  - Mantener descripciones cortas para no exceder límites de GPT Actions.

- [ ] Mejorar esquemas de respuesta OpenAPI.
  - Definir modelos de respuesta para exec, jobs, archivos, shares, artefactos, inventario, habilidades, auditoría y errores.
  - Estandarizar `ok`, `request_id`, `operation_id`, `warnings`, `truncated`, `artifacts` y `next_steps`.

- [ ] Ampliar pruebas de humo.
  - Probar health, auth, exec, write/read, background job, share, audit, artifacts y resetWorkspace dry-run.
  - Soportar ejecución contra host local y host HTTPS publicado.
  - Agregar prueba opcional para Nginx, Certbot, firewalld y renovación dry-run.

- [ ] Agregar documentación por escenarios.
  - Ejemplos para administración básica de entornos, diagnóstico, generación de reportes, Cloudflare DNS, Telegram, Playwright, contenedores, bases de datos, IaC e IA local con Ollama.
  - Incluir recomendaciones de seguridad, alcances de tokens, retención de auditoría y limpieza.
