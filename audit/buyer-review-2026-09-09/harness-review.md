# Harness y smoke de integración sin proveedor — 2026-09-09

**PASS del smoke local de protocolo, no de capacidad pública.** Se reemplazó el harness que podía medir respuestas rechazadas como éxito. No se modificó API/Bridge core ni se operó sobre DB/Redis/NATS reales.

## Cambios funcionales

- `scripts/run-load-isolated.py` crea una DB única `agora_test_load_*`, contenedores Redis/NATS propios desde imágenes locales y directorio privado efímero. Aplica migraciones solo a esa DB y ejecuta API propio. Desactiva scheduler/outbox persistente y acciones económicas sintéticas; no hace pull ni llamadas de modelo. Limpia exclusivamente sus recursos.
- `scripts/load_harness.py` se niega antes de conectar a usar DB por defecto, brokers compartidos, producción, provenance real o directorio sin marca de propiedad. Comprueba también el nombre real de DB conectado.
- Registra con firma Ed25519, obtiene reglas y atestigua entrada. Verifica2xx y contenido JSON; errores HTTP/aplicación/JSON-RPC terminan como FAIL y no cuentan como latencia de éxito.
- WS valida identidad de welcome y negocia bridge_capabilities protocolo2 con ACK antes de recibir trabajo. La presencia compara IDs exactos de los agentes creados, no el tamaño de una lista que pueda contener terceros.
- Heartbeat mide ACK real y conteo SQL completo de eventos antes/después, tomado después de entradas explícitas. No usa paginación como contador del ledger.
- Mensajes exigen recibo con event_id y read-after-write único. A2A verifica recepción real del task, claim durable con UUID, aceptación del claim, resultado determinista con el mismo UUID, ACK y lectura del estado terminal con artefacto. No presenta envío de solicitud como ejecución completada.
- Métricas p50/p95/p99 incluyen conteo; muestras vacías producen null. RSS se limita al proceso API, sin atribuirle memoria de toda la plataforma. Salida sanitizada sin sesiones, claves, IDs de participantes ni contenidos reales.

## Comandos y resultados

Desde raíz del repositorio:

```bash
AGORA_ENV=test .venv/bin/python -m pytest tests/unit/test_load_harness.py --noconftest -q
.venv/bin/ruff check scripts/load_harness.py scripts/run-load-isolated.py tests/unit/test_load_harness.py
HARNESS_OUTPUT=/home/merari-acero/agora/audit/buyer-review-2026-09-09/protocol-smoke.json .venv/bin/python scripts/run-load-isolated.py
```

Resultados reales: **16 tests pasaron**, Ruff `All checks passed!`, wrapper exit0. `protocol-smoke.json`:2 registros atestados,2 conexiones,2 presencias exactas,4 ACK de heartbeat, delta0 eventos,2 mensajes persistidos y1 resultado A2A fixture completado y leído. Duración del tramo de protocolo1.300s; RSS API128.45MB. Con tan pocas muestras, los percentiles son observaciones del smoke, no estimadores útiles de carga alta.

Run ID `load_b2c30f3d2c1a7607`. Limpieza independiente: consulta de catálogo DB devolvió `0` para su nombre exacto; `docker ps -a` filtrado por su etiqueta no devolvió contenedores. Ningún flush de Redis compartido.

## Límites pendientes

No mide24h, clientes remotos, caída/reconexión, pérdida de red, carga distribuida, tolerancia del broker, coste de inferencia, egress o HA. A2A usa fixture controlado, no modelo ni tarea científica. Rate limits se elevan solo dentro de este entorno de prueba y se declara en JSON. El harness falla al primer error; no produce una distribución completa de tasas de error bajo estrés. Para pruebas estadísticas debe extenderse a tasas/ventanas y clientes externos, conservando contadores separados y aislamiento.

El runbook `gcp-pilot-runbook.md` explica los pasos y dependencias concretas del piloto, incluido empaquetado local ya verificado en infra/pilot y adaptador GCS aún pendiente. No se ha realizado despliegue ni se ofrece capacidad garantizada.
