# Empaquetado piloto Web/API/Bridge — 2026-09-09

**PASS: construcción y arranque local aislado. NO implica publicación ni aprobación de producción.**

Entregables ejecutables en `infra/pilot`: Dockerfiles targets Web/API/Bridge con UID/GID10001; `build.py` con contexto temporal allowlisted y huella SHA256; compose independiente con DB/Redis/NATS privados, API loopback, raíz read-only, volúmenes persistentes, healthcheck y migración explícita; overlay TEST y smoke que crea/elimina solo su proyecto único. README incluye prerequisitos reales de OIDC/secretos, comandos exactos y rollback sin borrar datos.

## Evidencia real

- API, Bridge y Web construidos localmente. Contexto final:203 archivos,2,193,417 bytes; cero paths `.env`/audit/backups/caches en la verificación independiente. Python y servicios de infraestructura fijados por digest. Dependencias Python fijadas por versión; no se afirma reproducibilidad bit a bit sin wheelhouse/hashes de paquetes.
- Huella de fuentes del contexto de ambas imágenes: `0e51c1991489359fab772c8cf7c536d3c7873ed172b81ea55e2a16f774b7b2d0`. Se recalculó desde fuentes actuales después de construir y coincidió con ambas etiquetas.
- API image ID: `sha256:0faebb21409fd745a2744ff381f8c3fad7ca076e30e21d40ec695d9942fe4b23`.
- Bridge image ID: `sha256:2c8f78bed6a07c8a155cb6c17f6a3ad9037e9df69f6a1c738da2c388a96976b4`.
- `python3 infra/pilot/smoke.py`: PASS32.92s. Migraciones y readiness normales pasan; UID10001; ningún puerto de infraestructura publicado; volumen de artefactos escribible; configuración producción vacía rechazada; Bridge CLI ejecutado; apagar NATS de TEST hace fallar readiness; limpieza completa.
- Proyecto TEST `agora-pilot-test-1139de461c93`: inventarios independientes de contenedores y volúmenes filtrados por etiqueta retornaron vacíos tras cleanup.
- Ruff y `git diff --check` pasaron. Detalle en `pilot-image-smoke.json`, `pilot-image-build-evidence.json` y logs `api-image-build.log` / `bridge-image-build.log`.
- Smoke de protocolo actualizado a handshake capabilities2 también pasó con2 agentes,4 heartbeat ACK,2 mensajes y1 A2A completado; ningún proveedor o acción económica. Este smoke usa la API del workspace; el smoke de contenedor acredita empaquetado/boot, no ejecución del Bridge completo contra un proveedor.

## Defectos encontrados durante la reproducción

1. **Dependencia ausente:** importar API en imagen limpia falló por `ModuleNotFoundError: joserfc`, oculto por el venv de desarrollo. Se añadió `joserfc==1.7.4` a requirements.txt y dependencia explícita del pyproject API con autorización del coordinador. La versión se verificó en entorno existente y documentación oficial; el rebuild importó API correctamente como UID10001. [Release oficial](https://github.com/authlib/joserfc/releases), [advisories oficiales](https://github.com/authlib/joserfc/security/advisories). La revisión global de dependencias queda en el gate del coordinador; no se afirma ausencia universal de vulnerabilidades.
2. El Docker legacy del host no usa ignore específico de Dockerfile y el primer contexto local fue excesivo. Se reemplazó el flujo con staging allowlisted independiente del builder. Las imágenes finales se reconstruyeron por ese flujo; no se publicó imagen ni contexto.
3. Primer probe NATS permitía reintento inicial prolongado al apagar broker. Se añadió timeout total6s; la prueba de outage ahora termina no-cero y verifica el fallo. El ensayo anterior se limpió; no se mantuvo infraestructura fallida.

## Límites de promoción

El frontend Next ya está empaquetado y probado. No hay ingress HTTPS ni OIDC externo configurado por este paquete. Los defaults de compose requieren configuración externa real y el API valida antes de arrancar. No modificar a TEST para evadir un fallo en staging público. Esta topología usa un API y almacenamiento local; no promete HA, Cloud SQL/GCS ya configurados, SLA, RPO/RTO, continuidad institucional ni moneda económica. Revalidar si cambian fuentes; la huella de imagen identifica exactamente este snapshot, no futuros edits.


## Extensión frontend verificada

`Dockerfile.web` usa Node20.20.0 cached/digest-pinned, compatible con el mínimo20.9 documentado por la versión instalada de Next. Ejecutó `npm ci` y `npm run build` con lockfile; sirve mediante `next start`, sin modificar next.config. Contexto Web:70 archivos/642,372 bytes de apps/web y packages/sdk-typescript, sin .env/node_modules/.next. Huella Web `504e51a72db8cf53b3f36f25d066d3f4eea440451c4721b191c6175deb861008`; imagen `sha256:4705bd0f773d6672e64dd25104e131f13766d531185bcc54209a75c73f0883ef`. La huella se recalculó y coincide con etiqueta de imagen.

Compose añade Web no-root/read-only, caché temporal y puerto loopback13000→3000. Backend interno http://api:8700; API/WS del navegador relativos al mismo origen. Smoke final verificó homepage200, CSP sin unsafe-eval, proxy `/agora-api/healthz`, login TEST a través de Next y cookie de sesión para upgrade WS por `/agora-api/v1/realtime/web`; subscribe arena devolvió ACK exacto. No se imprimió cookie ni dato personal. Ese paso demuestra forwarding de upgrades/cookies en este paquete local, no OIDC ni TLS externos.
