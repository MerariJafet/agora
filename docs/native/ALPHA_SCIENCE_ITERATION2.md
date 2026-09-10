# Segunda iteración científica: correcciones y puente nativo ejecutado

Resultado final `20260909205834-26893`: **9 passed in 4.76s**, Ruff PASS.
El informe ALPHA_SCIENCE_RESULTS.md queda como evidencia de primera iteración;
este documento describe cambios posteriores y sustituye sus limitaciones cuando
se aporta aquí una prueba nueva concreta.

## Plan derivado del primer informe y ejecución

1. Etiquetar honestamente procesos Python, sin atribuir trabajo a Codex/Claude.
2. Llevar los seis paquetes científicos verificados a transiciones nativas reales,
   con firmas y claves distintas a las identidades AGORA.
3. Probar autorización, no emisión con dictamen negativo, bloqueo, challenge,
   maduración temporal simulada, transferencia y replay exacto.
4. Agregar señales de similitud y dueño común exclusivamente para revisión.

## Corrección de proveedor TEST

La API, esquema JSON y restricción SQL permiten ahora `python-scripted-test`.
Dos revisores de ese tipo forman un panel explícitamente sintético, manteniendo
actores diferentes, papeles de reproducción/falsificación, comprobaciones de
conflictos y compromisos ciegos. Se conserva compatibilidad con Codex/Claude.

La primera corrida de esta iteración detectó que la columna VARCHAR(16) y su
CHECK no admitían la etiqueta honesta: **6 fallos, 2 aprobados**. Se preserva su
log. Migración **0038_python_test_reviewer**, aplicada exclusivamente por el
wrapper sobre bases temporales, amplía a VARCHAR(32) y el CHECK. El registro
humano de instituciones no cambia. El downgrade está diseñado para rechazar
si permanecen revisores Python; nunca los convierte en otro proveedor ni borra
historia. No se ejecutó downgrade sobre datos existentes.

Después de corregir el contrato persistente: 8 aprobados en 4.70 s; tras mapa de
contribuyentes y prueba de señales: 9 aprobados en 4.69 s. La revisión adicional
alineó los hashes exportados al dominio `tokoin.state.v2` utilizado por ABCI y
conservó las transacciones rechazadas completas. Corrida final: 9 aprobados,
4.76 s. Las ejecuciones anteriores permanecen en campaign-index.json.

## Integración AGORA → aplicación TOKOIN

Cada caso produce un paquete vía `/reproducibility-package`, recalcula su hash
con el verificador offline y usa la genealogía real de ese candidato. El manifiesto
monetario compromete el informe computado, hashes de revisiones AGORA, artefactos
ejecutados, código y distribución. Se exporta su preimagen para reproducirlo.

Se generan seis claves nativas efímeras, separadas de claves AGORA: dos revisores,
solver, replicador, infraestructura y proponente. Los mapas públicos vinculan
actores/contribuciones/hashes con direcciones y claves. Son mapas de fixture TEST,
no una prueba de titularidad institucional humana. El payout de contribuyentes
usa dos unidades de trabajo TEST (experimento ejecutado y réplica ejecutada),
no mensajes ni votos. Se conserva 10/10/51/20/9 y el reward fijo TEST de 1 TOKOIN.

| Caso | Resultado monetario de la aplicación nativa |
|---|---|
| SCI-001 | Dos reviews aprobados → autorización → LOCKED; transferencia precoz rechazada; finalización al límite simulado y transferencia válida |
| SCI-002 | Mismo flujo; challenge admitido bloquea finalización; rechazo posterior reanuda plazo; finaliza y transfiere |
| SCI-003 | Reviews insuficientes; autorización rechazada y suministro cero |
| SCI-004 | Reviews rechazan fabricación; autorización rechazada y suministro cero |
| SCI-005 | Revisiones exigen corrección; autorización rechazada y suministro cero |
| SCI-006 | Rechazo documentado y reconocible; autorización rechazada y suministro cero |

SCI-001 y SCI-002 usan **génesis separados**, cada uno emite 100000000 unidades
TEST. No son dos emisiones consolidadas en una red económica. Cada génesis parte
de cero. Se reconstruyen las seis secuencias desde génesis y se comprueba igualdad
canónica exacta del estado. Se exportan corpus firmado, AppHashes y rechazos.

El challenge de SCI-002 es una prueba procedural explícita: evidencia n=9 contra
la hipótesis rival se admite a análisis y luego se rechaza por no refutar el conteo
aceptado. No se inventa un descubrimiento ni se afirma que esa impugnación invalide
la conclusión correcta.

**Capa probada: NATIVE_APPLICATION_TIME_SIMULATION_NOT_NETWORK_OR_REAL_YEAR.**
Se usa la función nativa determinista de transición, no RPC CometBFT ni espera real
de 365 días. Las credenciales representan roles TEST bajo el mismo operador. No
se declara independencia humana o consenso científico validado en el mundo real.

## Señales WS-08

`local_alpha_science_signals.py` limita el tamaño del corpus; detecta copia
normalizada, similitud de caracteres y agrupaciones de votos de agentes con dueño
conocido común. La salida dice REVIEW_ONLY: no condena, bloquea ni penaliza. La
prueba evita duplicar agentes por votos repetidos y no infiere dueños desconocidos.
Es una herramienta de revisión, no un detector semántico completo ni solución Sybil.
No está conectada automáticamente al servicio productivo ni a cambios económicos.

## Evidencia y reproducción

Directorio final:
`audit/local-alpha-v02/science/20260909205834-26893/`

68 artefactos enumerados mediante SHA-256, incluyendo seis
`native-application-e2e.json`. Escaneo acotado de cuatro patrones: cero hallazgos
sobre este directorio. Claves privadas permanecen en memoria, no en los paquetes.

```bash
scripts/run-isolated-tests.sh tests/integration/test_local_alpha_science.py tests/integration/test_research_protocol_institutional_validators.py -q --tb=short
.venv/bin/ruff check scripts/local_alpha_science*.py tests/integration/test_local_alpha_science.py apps/api/alembic/versions/0038_python_test_reviewer.py apps/api/agora_api/institutional_validator_service.py
```

Pendiente fuera de esta prueba: misiones creadas autónomamente por API, agentes
LLM reales, flujo científico completo transmitido a nodos por red, adopción humana,
credenciales externas, falsificación general de citas, resistencia Sybil y
reconocimiento económico no TEST. La máquina científica API conserva
EVIDENCE_REVIEW_REQUIRED para inconclusos; no se añadió un nombre de estado nuevo.

## Cierre adicional: compatibilidad y migración verificadas

Regresiones institucionales, protocolo de investigación, exportación canónica y
seguridad de knowledge ledger/research market: **25 passed in 3.38s**. Incluyen
el panel Codex/Claude previo y sus controles de independencia/commit-reveal.

Prueba separada sobre otra base nueva creada por el wrapper: **1 passed in 1.01s**.
Se ejecutó downgrade 0038→0037 y upgrade 0037→0038, verificando en PostgreSQL el
número de revisión, tamaño de columna (16/32) y CHECK de proveedores (Codex/Claude
siempre conservados; Python únicamente en 0038). Esta prueba usa tabla vacía;
no demuestra migración hacia atrás con registros Python existentes. No se modificó
la base viva. Evidencia: `audit/local-alpha-v02/science/iteration2-closure/`.

**Pendiente económico explícito:** el recibo firmado de un reviewer que rechaza
es reconocimiento auditable de trabajo, **no compensación monetaria** independiente
del veredicto. El protocolo monetario congelado sólo remunera revisores dentro de
un reward científico elegible con aprobaciones compatibles. No existe en esta
entrega un camino monetario separado para revisión rigurosa negativa. Inventarlo
alteraría tokenomics; se deja pendiente de diseño y aprobación del protocolo.
Por tanto, no debe declararse resuelto el incentivo económico a rechazar; lo
probado es que el sistema preserva y reconoce documentalmente ese trabajo sin
forzar aprobación ni crear tokens indebidamente.

Comandos adicionales de reproducción:

```bash
scripts/run-isolated-tests.sh tests/integration/test_research_protocol_institutional_validators.py tests/integration/test_research_protocol.py tests/unit/test_research_export.py tests/unit/test_institutional_validator_pilot.py tests/security/test_magna_knowledge_ledger_security.py tests/security/test_research_market_security.py -q --tb=short
scripts/run-isolated-tests.sh tests/integration/test_local_alpha_science_migration.py -q --tb=short
```

La prueba de migración requiere su invocación separada con base nueva, porque
comprueba explícitamente ausencia de revisores antes del downgrade.

## Corrección de aislamiento detectada por la suite completa

Primera ejecución amplia: **599 PASS, 2 FAIL, 66.26 s**. Se preservó en
`audit/local-alpha-v02/iteration-2/api-suite-full.txt`. Ambos fallos provenían de
supuestos de aislamiento de los tests nuevos: el test de migración esperaba tabla
vacía, y el bootstrap de SCI afectaba al test posterior que comprueba una base sin
constitución. No se relajaron las aserciones de producción ni del test constitucional.

Corrección exclusivamente en tests: cada escenario científico usa transacción
exterior y savepoints para los commits reales del API, exporta evidencia y revierte
sus filas. Comprueba igualdad de conteos antes/después en agents, missions,
institutional_validators y root_constitutions. La migración crea su propia sub-base
`agora_test_migration_*`, únicamente dentro del wrapper verificado, y la elimina al
final. Ya no requiere ejecutar el test por separado de la suite general.

Regresión conjunta: **15 PASS, 8.14 s**. Suite amplia repetida sin exclusiones:
**601 PASS, 68.51 s**. Ruff aprobado; consulta final encuentra cero sub-bases
`agora_test_migration_*` restantes. No se modificó núcleo nativo ni base viva.

Evidencia completa corregida:
`audit/local-alpha-v02/iteration-2/api-suite-full-corrected.txt` y
`audit/local-alpha-v02/iteration-2/api-suite-full-corrected.xml`.
