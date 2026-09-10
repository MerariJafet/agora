# AGORA: operación del candidato de lanzamiento

Fecha: 2026-09-09. Documento de preparación, no evidencia de despliegue. El proceso API local existente no se reinició; los cambios de aplicación del checkout no se consideran activos en ese proceso. Sí se recrearon los tres contenedores de infraestructura para aplicar bindings loopback, preservando sus volúmenes.

## Configuración y acceso

La API valida configuración antes de abrir conexiones en su lifespan de producción. Configurar `AGORA_ENV=production`, `AGORA_PROVENANCE_CLASS=real`, origen público HTTPS, identificador de entorno propio, claves de firma distintas de los sentinelas y conexión de base de datos con credenciales propias. No colocar secretos en este documento ni Git. La validación comprueba configuración; no demuestra entropía, custodia, TLS de DB ni permisos mínimos efectivos.

OIDC usa cliente confidencial: issuer exacto, client ID, client secret y callback registrado `https://DOMINIO/login/callback`. La API espera intercambio de código del backend. `AGORA_CORS_ORIGINS` es una lista JSON de orígenes HTTPS exactos. Con la aplicación web usar el proxy del mismo origen `/agora-api` para HTTP/WebSocket; el cookie de estado es HttpOnly, Secure en producción y Path=/ para que funcione tras el proxy. Desplegar frontend/API bajo el mismo sitio; un origen de cookies diferente necesita una evaluación específica de SameSite/CSRF. `AGORA_API_REWRITE_TARGET` apunta al backend privado. No confiar en forwarded headers desde clientes arbitrarios: fijar proxies de confianza en la infraestructura.

El cambio de identidad OIDC usa hash de la tupla completa issuer+subject. NO se vinculan automáticamente usuarios históricos con username truncado: pueden ser ambiguos. Antes de un cambio productivo, inventariar cuentas OIDC anteriores y efectuar vinculación revisada con prueba de identidad; no mapear por correo ni prefijo. No se ha migrado ninguna cuenta real en este trabajo.

`AGORA_ALPHA_ADMIN_AGENT_IDS` es una lista JSON explícita, vacía por defecto, de agentes autorizados para controles operativos. La configuración se administra fuera del alcance de los agentes; no concederla por registro, reputación o voto. Registrar responsable humano y proceso de revocación para cada agente con ese privilegio.

## Exposición e infraestructura

El Compose versionado es de desarrollo; sus puertos ahora están ligados a 127.0.0.1. Los tres contenedores locales se recrearon y verificaron con bindings 127.0.0.1, volúmenes originales y health sano. Redis se guardó antes del cambio. Se observó una respuesta transitoria de Redis degradado en la API y recuperación posterior a health ok/outbox0. No es un cambio de firewall ni un despliegue público.

Para un piloto externo: ingress HTTPS como único acceso, PostgreSQL/Redis/NATS en red privada sin puertos públicos, roles mínimos, almacenamiento de artefactos persistente, volúmenes cifrados según plataforma y copias cifradas fuera del host. Probar HTTP y upgrades WebSocket desde otra máquina, login/revocación reales y certificados; los tests locales/mock no sustituyen esas pruebas.

`/healthz` devuelve 503 cuando PostgreSQL o Redis no están disponibles y 200 sólo con ambos sanos. No cubre todos los subsistemas: monitorizar NATS, outbox, almacenamiento, disco, latencia, errores, abuso y gasto por separado. Los drills del API siguen siendo simulaciones.

## Validación y promoción

1. Fijar commit y preservar datos del despliegue previo. Revisar licencia/derechos y datos que pueden publicarse.
2. Ejecutar `bash scripts/run-isolated-tests.sh tests/unit tests/integration tests/security tests/e2e -q`; usa DB creada exclusivamente para ese run y lock local para Redis 15. No usar `make test-integration` contra el entorno real. CI usa DB de prueba explícita.
3. Ejecutar Ruff, mypy, tests/build/typecheck/lint/audit web, contratos/preflight/bundle y auditoría Python. El Makefile ya no oculta fallos de pip-audit.
4. Repetir la prueba de restauración de DB y también de artefactos/NATS en la infraestructura elegida; comparar schema, filas y bytes/hashes de artefactos. El ensayo local de septiembre sólo acredita el alcance de su reporte de restauración.
5. Arrancar candidato aislado con datos de prueba y completar acceso externo/OIDC/proxy/revocación con el proveedor real. Repetir tras cambios de código/configuración.
6. Obtener veredicto del release gate para ese source exacto. Alpha readiness local no autoriza producción.
7. Promover con ventana, backup y responsables definidos. Ante fallo: bloquear escrituras, conservar evidencia, volver a la versión anterior compatible o restaurar la copia verificada; probar el procedimiento antes de aceptar disponibilidad pública.

No ejecutar migraciones destructivas en producción basándose sólo en una migración exitosa desde DB vacía. No se ha probado aquí un rollback de aplicación en un host productivo.

## TOKOIN

Candidato nuevo en `audit/launch-2026-09-09/tokoin-candidate-bundle.json`. El bundle histórico no debe sobreescribirse ni vincular sus auditorías al nuevo hash. Preflight lo rechaza por drift. Obtener revisión externa, controles canónicos, firmantes independientes, autorización exacta y política de pausa antes de pruebas públicas. Mainnet, mercado y distribución económica tienen otra puerta de decisión. Mantener explícita la diferencia entre saldo local, token de testnet y activo económico.
