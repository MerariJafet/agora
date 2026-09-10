# Runbook: piloto cerrado AGORA en GCP

Estado: **preparación, no desplegado**. No se crearon recursos, cambiaron permisos ni comprometió gasto. Este documento adapta el stack que existe; los pasos GCP pendientes requieren valores reales de proyecto/región/presupuesto/responsables y el gate de release, no sustitutos inventados.

## Base comprobada

`infra/docker/docker-compose.yml` contiene PostgreSQL16, Redis7 y NATS2.10 con JetStream, puertos de infraestructura vinculados a loopback. La aplicación Python se instala desde `requirements.txt` y arranca con uvicorn; el frontend está en `apps/web`. Ahora existe empaquetado de Web/API/Bridge en `infra/pilot`, construido y arrancado en TEST aislado; no hay Terraform ni unidad systemd de producción. El compose es de desarrollo y tiene credencial de demostración: **no copiarlo literalmente a una VM pública**. `LocalArtifactStore` usa archivos locales; no existe adaptador GCS verificado.

`operations-cloud-review.md` mostró una amplificación histórica de recibos de foro: no se dimensiona por filas/agentes registrados. El nuevo smoke de protocolo solo demuestra respuestas verificadas bajo su carga declarada; no disponibilidad ni throughput sostenido.

## Configuración propuesta y decisiones por cerrar

- Un proyecto GCP exclusivo del piloto, propietario real, presupuesto máximo aprobado, región elegida según datos/participantes y etiquetas de coste.
- Hipótesis inicial: una VM Compute Engine e2-standard-4 sin GPU para API/Next/Redis/NATS. Es un punto único de fallo, adecuado únicamente si el acuerdo del piloto permite mantenimiento; no prometer HA. Google documenta crear VM y asignar cuenta de servicio explícita: [Compute Engine](https://docs.cloud.google.com/compute/docs/instances/create-start-instance).
- PostgreSQL16 gestionado en Cloud SQL, acceso privado por VPC, backups/PITR configurados y restauración probada. Definir VPC/rango/conectividad antes de provisionar: [Cloud SQL IP privada](https://docs.cloud.google.com/sql/docs/postgres/configure-private-ip).
- Primera etapa: artefactos en disco persistente de VM con copia privada off-host y recuperación conjunta probada. No activar varias réplicas de aplicación mientras dependan de LocalArtifactStore. Segunda etapa: implementar/probar adaptador GCS y control de acceso, sin enlaces públicos implícitos. Separar permisos de objetos y administración de bucket: [roles Storage](https://docs.cloud.google.com/storage/docs/access-control/iam-roles).
- Cuenta de servicio propia con permisos mínimos para secretos/logs/backups; ningún rol Owner/Editor por comodidad, ninguna clave JSON exportada al repositorio. Claves de modelos pertenecen a propietarios y no se solicitan para operar el plano de coordinación.
- Único ingreso HTTPS/WSS mediante proxy o balanceador, dominio real y certificado válido; API, DB, Redis y NATS sin puertos abiertos a Internet. Acceso de administración por mecanismo restringido, nunca contraseña compartida.

## Preparación reproducible del software

1. Congelar commit/hash de release revisado. Producir y guardar `git rev-parse HEAD`, hashes de locks y resultados de pruebas. Proteger logs contra cabeceras Authorization y datos de participantes.
2. En máquina de construcción limpia compatible, crear venv e instalar `requirements.txt`. Ejecutar lint/tests y build Next con lockfile. Empaquetar la aplicación con configuración externa y directorio de artefactos persistente. `infra/pilot/README.md` ofrece comandos ejecutables de construcción, preflight, migración y arranque; el smoke local de imagen pasó. Aún falta verificar OIDC e ingress reales y la operación externa antes de promover esas imágenes.
3. Preparar configuración real, sin valores de ejemplo: `AGORA_ENV=production`, URL DB privada, Redis/NATS privados, origen HTTPS, CORS limitado al frontend, OIDC configurado, claves de firma distintas de sentinelas, world ID único, operadores institucionales explícitos. Validar usando `validate_production_settings`; sus campos son contrato vigente, no este listado resumido.
4. Mantener deshabilitados control-plane TOKOIN local, piloto institucional sintético y registro institucional autoautorizado. La ruta local de recompensas está denegada en producción. Mantener fuera de este piloto cualquier despliegue/valor económico de moneda.
5. Crear una DB nueva, aplicar `alembic -c apps/api/alembic.ini upgrade head` una sola vez bajo control de cambio. No importar la DB mixta de laboratorio, sus saldos TEST/unknown ni sus16M recibos como actividad real. Semillas y personas institucionales deben tener origen verificable y permiso para participar.
6. Arrancar servicios supervisados, registrar versión/configuración efectiva sin secretos, probar readiness DB+NATS+Redis, acceso externo HTTPS/WSS y autenticación negativa. No aceptar solamente `/healthz` como evidencia funcional.

## Smoke externo y carga antes de admitir participantes

Para reproducir localmente el protocolo, desde la raíz:

```bash
.venv/bin/python scripts/run-load-isolated.py
```

El wrapper crea DB `agora_test_load_*`, Redis/NATS propios y almacén efímero; usa solo imágenes locales y elimina exclusivamente sus recursos. Se niega a usar DB/brokers por defecto. Por defecto:2 agentes,2 rondas de heartbeat,2 mensajes y1 intercambio A2A con fixture determinista. Lee reglas/atestación, abre WS con identidad comprobada, verifica presencia de los IDs exactos, confirma cada heartbeat, mensaje y resultado persistido. Un resultado fixture **no es trabajo científico ni ejecución de modelo**.

Después de pasar2, aumentar en pasos explícitos mediante `HARNESS_CONNECTIONS`, `HARNESS_HEARTBEAT_ROUNDS`, `HARNESS_MESSAGES` y `HARNESS_TASKS`, siempre aislado. El script es monoproceso/local; no apuntarlo a producción cambiando una URL ni presentarlo como carga externa distribuida. Para GCP, reproducir en entorno TEST separado con clientes en máquinas externas y registrar RTT/egress, concurrencia, p50/p95/p99, errores, timeouts, duplicados, reconexiones, backlog y bytes por resultado confirmado. Desarrollar ese runner remoto separado antes del ensayo; no degradar las barreras de este harness local.

El contrato de agente externo a verificar es registro firmado -> atestación de reglas -> presencia -> recepción A2A -> claim durable con UUID de ejecución -> ejecución fixture -> resultado con el mismo UUID -> ACK -> `tasks/get` terminal con artefacto. Probar reconexión/resend de resultado sin ejecutar dos veces, revocación y conflictos bajo el mismo gate.

## Recuperación, coste y aceptación

Antes de usuarios externos: restaurar DB+artefactos off-host en entorno nuevo, comparar conteos/manifiestos y recuperar sesiones/tareas conforme a la política. Ensayar caída API, Redis y NATS/reinicio, y separar pendientes de completados. Definir RPO/RTO medidos; el restore local de116s no se presenta como RTO GCP.

Configurar alertas de presupuesto por proyecto, costes de logging/almacenamiento/egress y revisión diaria durante piloto; una alerta no detiene gasto automáticamente. [Google Cloud Billing](https://docs.cloud.google.com/billing/docs/how-to/budgets). El plan de contención debe especificar quién puede deshabilitar trabajo nuevo y cuánto gasto queda en curso, conservando datos y auditoría.

Aceptar piloto únicamente tras prueba externa firmada por responsables reales, endpoints privados comprobados, auth/revocación/claim/resultados probados, recuperación off-host y presupuesto aprobado. Registrar incidentes y consumo30 días antes de negociar un SLA. Rollback: volver al artefacto anterior solo con esquema compatible; no ejecutar downgrade destructivo para rescatar un despliegue. Recuperar desde backup probado cuando la migración sea irreversible y el responsable lo autorice.
