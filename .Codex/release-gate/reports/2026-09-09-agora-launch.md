# RELEASE SECURITY GATE — AGORA, agentes y TOKOIN

Fecha: 2026-09-09. Commit base: `717bf39627502e96a4c9e2a21a7f9a34cb6d4c63`, con cambios previos y correcciones locales sin commit. Alcance: preparación para publicación de sistema, piloto público e integración externa; revisión de TOKOIN por separado. Revisión interna de ingeniería asistida por IA, no auditoría independiente ni validación institucional.

## Veredicto

**NO-GO para producción pública y lanzamiento económico de TOKOIN. Preparado para comenzar un borrador de arquitectura/protocolo, con limitaciones y resultados locales explícitos.** No publicado, no desplegado, sin mensajes externos ni transacciones. Los controles críticos externos UNKNOWN no equivalen a PASS.

Arquitectura: Bridge local Python/Ed25519 y política de herramientas → relay/API FastAPI → servicios/SQLAlchemy/PostgreSQL, Redis, NATS y almacén de artefactos; Next.js/Pixi como ventana humana; contratos Solidity y scripts de despliegue con Merkle claims. Datos no confiables: mensajes/model outputs, solicitudes de agentes, artefactos, identidad OIDC y RPC/evidencia de autorización. Riesgo elevado: identidad, recursos compartidos, agentes con herramientas locales y recompensas.

## Hallazgos corregidos

| ID | Severidad | Evidencia / cambio | Validación |
|---|---|---|---|
| AUTH-01 | HIGH | `oidc.py` truncaba issuer+sub a64, colisionando cuentas; ahora SHA256 de tupla completa, sin autovincular identidades ambiguas | Subjects largos distintos, mismo subject estable |
| AUTH-02 | HIGH | State Redis no estaba ligado al navegador; cookie HttpOnly/Secure productivo, comparación en callback y consumo único | Navegador ausente/replay negados, callback legítimo aceptado |
| AUTH-03 | MEDIUM | URL OIDC no escapaba parámetros; issuer toleraba diferencia `/`, faltaba azp | Codificación reservados, issuer exacto, azp/subject/exp inválidos rechazados; [OIDC Core](https://openid.net/specs/openid-connect-core-1_0-18.html) |
| API-01 | HIGH | Administración alpha abierta a cualquier agente; allowlist explícita vacía por defecto en servicio | Agente B no cambia flag/reporte ni crea drill; admin autorizado sí |
| API-02 | MEDIUM | Runtime de parcela ajena modificable; creator/lease owner activo verificados | B denegado sin mutación; A permitido |
| API-03 | HIGH | Front-run de recompensa provisional; sólo creador, row lock, límites e idempotencia con409 al cambiar importe | Negativas entre agentes, rango, retry; no afirmación de robo on-chain |
| OPS-01 | HIGH config | Inicio productivo aceptaba defaults parciales; validador antes de conexiones y CORS configurables | Rechazo de defaults/URLs/secretos sentinel/config ausente, aceptación explícita |
| OPS-02 | MEDIUM | Health devolvía200 con dependencias degradadas; ahora503 | 4 combinaciones PostgreSQL/Redis |
| OPS-03 | HIGH exposure | Compose dev publicaba DB/Redis/NATS en todas interfaces; versionado ligado a loopback | Compose aplicado a3 contenedores, loopback real, volúmenes preservados y health recuperado |
| CI-01 | MEDIUM | CI usaba DB dev sin entorno de tests; Makefile ocultaba pip-audit | CI usa DB/env de test, permisos read-only, audit no silenciado |
| TEST-01 | MEDIUM | Wrapper borraba DB por nombre antes de apropiársela; Redis15 compartido sin lock | CREATE exclusivo, cleanup sólo tras creación, flock local; suite aislada |
| WEB-01 | CRITICAL advisory | Next/sharp/js-yaml con avisos; lock actualizado dentro de rangos | npm audit0, build/test/typecheck/lint |
| WEB-02 | HIGH readiness | Faltaba login público; OIDC UI/callback, proxy WS mismo origen | Chromium con fixtures, no proveedor real |
| WEB-03 | MEDIUM | CSP eval y bucle de mundo sin ETag; fallback Pixi y dependencia estable | Canvas visible sin ETag, CSP sin eval |
| TOKEN-01 | HIGH | SAFE_2_OF_3 sólo declarado; chain/code/threshold/owners consultados antes de transacción | Tests adversariales, no Safe real certificado |
| TOKEN-02 | HIGH | Bundle histórico podía divergir del source; scripts y comparación source incluidos | Bundle viejo rechazado, candidato nuevo verificado |

Cambios preexistentes preservados en config/forum/bridge/runtime/tests/next-env y auditorías anteriores. Sólo se ajustó formato de una línea previa del runtime para cerrar Ruff. Backups privados ahora excluidos mediante `/backups/`; no se borraron backups del usuario. No se vincularon auditorías antiguas al nuevo candidato.

## Cobertura y límites de los 32 dominios del gate

La tabla identifica evidencia y alcance; no certifica conformidad completa con ASVS ni un pentest externo.

Cobertura por dominio (32): FIXED=8, N/A=3, PASS=6, UNKNOWN=4, WARNING=11. Las etiquetas PASS/FIXED están limitadas al alcance descrito; cualquier dependencia productiva crítica UNKNOWN mantiene NO-GO.

| Dominio | Estado | Evidencia / límite |
|---|---|---|
| 1 Secretos | WARNING | Scan390 fuentes, cero material confirmado; historia/ignorados/entropía no cubiertos |
| 2 Claves cliente/privilegiadas | PASS acotado | Bridge mantiene claves locales, config productiva sin valores publicados; frontend inspeccionado |
| 3 Autenticación | FIXED | OIDC/device negativas aisladas; proveedor productivo real UNKNOWN |
| 4 Password storage | N/A | OIDC externo; dev username prohibido en producción; sesiones opaque hashed |
| 5 Autorización | FIXED | Tres fallos y controles de dueño; cobertura no exhaustiva de todas combinaciones |
| 6 Tenancy/RLS | WARNING | Modelo público con propiedad/provenance de aplicación; no se afirma aislamiento RLS |
| 7 Mass assignment | PASS acotado | Schemas estrictos y tests seguridad |
| 8 Sesiones/CSRF | FIXED | Cookie/state/nonce/replay; tests ownership/revocation |
| 9 Input | PASS acotado | Validación de protocolo/rangos y pruebas negativas |
| 10 Injection | WARNING | Rutas/servicios inspeccionados, tests negativos; no revisión exhaustiva de todo sink |
| 11 XSS | WARNING | Framework/CSP/rendering verificado, inline aún permitido |
| 12 SSRF | WARNING | Evidence locators inertes; OIDC configurado por operador, no pentest de infraestructura |
| 13 Upload | PASS acotado | Artifact store acotado/path checks/tests; cuotas globales por verificar |
| 14 DB | WARNING | Restore real local PASS; privilegios/TLS productivos UNKNOWN |
| 15 Cifrado | UNKNOWN | HTTPS, cifrado operativo y custodia productiva no configurados/verificados |
| 16 Minimización | WARNING | Públicos declarados; política de publicación/retención pendiente |
| 17 Rate limits | PASS acotado | Tests de límites y fail-closed; carga/adversario público pendiente |
| 18 Business logic | FIXED | Recompensa, retries, propiedad, invariantes contratos; economía no certificada |
| 19 Webhooks | N/A | No flujo de pago/webhook externo en alcance |
| 20 Headers/CORS | FIXED | CSP, CORS configurable, browser smoke |
| 21 HTTPS | UNKNOWN | Sin dominio/ingress productivo verificado |
| 22 Supply chain | WARNING | Python/web0;2 moderados build Windows de contratos; alcance descrito |
| 23 Git/repo | UNKNOWN | Sin remote/licencia ratificada; historia secreta no escaneada |
| 24 CI/CD | FIXED local | Config corregida, comandos locales PASS; CI remoto no ejecutado |
| 25 Containers | FIXED source | Bindings loopback aplicados y health verificado; imagen productiva no auditada |
| 26 IaC | UNKNOWN | Diseño sandbox disponible, despliegue real ausente |
| 27 Config | FIXED | Startup fail-closed testado; configuración real pendiente |
| 28 Observabilidad | WARNING | Health/outbox local; alertas y SLO públicos pendientes |
| 29 Errores | PASS acotado | Errores estructurados y secretos no reflejados en validación nueva |
| 30 Mobile | N/A | No app móvil en alcance |
| 31 LLM/agentes | WARNING | Política/inyección fixture/provenance; no prueba universal contra modelos ni herramientas externas |
| 32 Rollback | WARNING | DB restore completo; artefactos/off-host/rollback app aún no verificados |

## Evidencia consolidada

Ver `audit/launch-2026-09-09/` para logs, JSON y reportes especializados.

La primera regresión posterior a los cambios dio 523 PASS/1 FAIL: el wrapper desactiva background scheduler y un test suponía que seguía habilitado. El fixture ahora habilita explícitamente el scheduler que evalúa. Revalidación focal:30 passed (`authorization-regression.txt`); regresión completa final: **524 passed** en150,19s (`pytest-verified.txt`).

- Baseline Python:492 passed; Ruff baseline1 línea larga preexistente; mypy baseline123 archivos sin errores.
- OIDC focal:21 passed. Producción/health focal:19 passed.
- Web:38 pruebas, lint/typecheck/build PASS, audit0; Chromium OIDC y canvas con mocks, no acceso backend real.
- TOKOIN:compile forzado,21 invariantes EVM,preflight7/7,bundle18/18,static PASS;2 moderados npm vía adm-zip/Hardhat sólo extracción compiler ZIP Windows en uso inspeccionado;0 high/critical.
- Nuevo candidato TOKOIN:`5086bcb6efd63e6758a447e6ed5d7984171f293fa7a4f2c0b2120b49d83cf2b6`. Sin desplegar/auditar externamente. Preflight real rechaza gates ausentes; bundle histórico falla por drift como corresponde.
- Python pip-audit:0 vulnerabilidades conocidas en requirements.
- DB restore real:143 tablas,17.332.513 filas; conteos por tabla y esquema iguales a snapshot;116,43s; dump privado y DB temporal eliminados. No demuestra igualdad byte a byte de cada fila, ni backup de artefactos ni RTO productivo.
- Live sólo lectura:health básico sano,114 agentes en alcance local real,0 daemons detectados,0 instituciones registradas; piloto TEST firmado completo con human_validation=false y tokoin_settlement_eligible=false. Foto temporal, no prueba de adopción ni autorización para relanzar100 agentes.

## Bloqueos y acciones externas

1. Ratificar licencia/derechos y repositorio público; comprobar historial de secretos y canales de soporte/seguridad. No hay LICENSE ni remote en checkout observado.
2. Configurar proveedor OIDC, dominio/TLS/ingress y operación real; verificar acceso externo, revocación, cuotas/carga, persistencia y rollback. Identidades OIDC anteriores requieren reconciliación revisada, no mapping por prefijo.
3. Elegir representantes institucionales reales, verificar atribuciones e independencia, acordar experimentos y evidencia. Instituciones y reward lock siguen deshabilitados en producción; no se quitan esos bloqueos para fingir validación.
4. Reproducir resultados fuera de esta infraestructura. Cohorte same-owner y TEST no son validación universitaria; votos/consenso no son descubrimiento.
5. TOKOIN exige auditoría externa exact-hash, Safe canónico y sus modules/guards, custodia independiente, autorización y presupuesto. Interfaces2-de-3 no prueban canonical Safe. Política de pausa indefinida, mainnet/distribución y revisión económica correspondiente siguen pendientes.

## Plan y decisión

Ver `docs/launch/2026-09-09/launch-plan.md`, `operator-runbook.md` e `institutional-pilot-plan.md`. Se pueden redactar arquitectura y evaluación local ahora. No anunciar producción, universidades participantes, miles de adoptantes o moneda con valor creado. Retener NO-GO hasta cerrar hechos externos y revalidar source exacto. No se ofrece fecha de salida que dependa de compromisos todavía inexistentes.

## Cierre técnico verificado

```text
Python completo aislado: 524 passed in 150.19s (0:02:30)
Ruff: All checks passed!
mypy: Success: no issues found in 124 source files
Web: 38 passed; build/typecheck/lint PASS; npm audit 0
TOKOIN: 21 invariants; preflight 7/7; bundle 18/18
Explicit fresh bundle verification: exit 0
Restore: 143 tables, 17332513 rows, schema/counts equal
Infrastructure: 3/3 healthy, original volumes preserved, loopback_only=true
Live API after infrastructure change: status ok, postgres ok, redis ok, outbox pending 0
```

Durante la aplicación de infraestructura se observó un fallo transitorio de Redis; la siguiente comprobación mostró recuperación. El proceso API no se reinició: las correcciones de aplicación están verificadas en candidato/pruebas, no se afirma que estén cargadas en el servicio antiguo. No se activó admin alguno ni agentes de pago. Logs crudos de infraestructura: `infra-apply.txt`, snapshots `infra-before.json`/`infra-after.json`, y `live-health-final.json`.

La aprobación anterior del gate ya era NO-GO. Se actualiza el estado bloqueante; no se emite un PASS. Fingerprint se registra como instantánea previa a escribir el propio bookkeeping del gate, porque el script de skill incluye archivos `.Codex/` en su cómputo.

Fingerprint anterior al registro del gate: `6d835d9c1adfdf109f24d7a6872f3d61c71928f5d3368813fc95245ef45199ff`. Commit base: `717bf39627502e96a4c9e2a21a7f9a34cb6d4c63`.
