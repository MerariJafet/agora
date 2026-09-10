# AGORA / TOKOIN V0.3 — resultados, mejoras y dictamen

La iteración local V0.3 está implementada y verificada como experimento reproducible. El flujo une agentes LLM reales, API científica, revisión ciega firmada y asentamiento por la red nativa. Esto habilita un candidato de paper sobre el experimento y la preparación del ensayo con operadores externos. No habilita una criptomoneda pública ni prueba descentralización, universidades participantes o sostenibilidad económica.

## Qué se reutilizó y qué cambió

Se conservó V0.2 (`aa21f2e6fac27362da1017ca5800a1ded1bdb7bf`), sus resultados y el motor CometBFT fijado. La inspección encontró que la campaña previa preparaba parte del reto mediante un fixture de base de datos. Se añadió creación autenticada por API exclusivamente TEST, con evento/outbox, provenance y commitment del contenido del reto. El código fuera de TEST rechaza ese endpoint. Las pruebas usan bases desechables; no se migró ni reinició el servicio vivo.

Se añadió una máquina científica nativa versionada, con identidades comprometidas en génesis, grafo de eventos, revisión commit/reveal, decisión, objeción y resolución, árbol congelado y dos fases de recompensa. Se preservan el cap, unidades enteras y reparto nominal 10/10/51/20/9. El pool de revisión se paga por trabajo admisible, también ante rechazo o inconclusión; el pool de resultado exige aprobación. Los saldos soberanos del experimento proceden de transacciones nativas, no de escrituras SQL.

## Primera ejecución → análisis → segunda implementación

| Hallazgo conservado | Mejora implementada | Evidencia de regresión |
|---|---|---|
| Conflicto de controlador podía ocultarse con otra declaración | Contraste con registro de génesis e identidad precomprometida | `security/adversarial-first.xml` → `security/adversarial-remediation-001.xml` |
| Resultado podía madurar con revisión impugnada o revocada | Dependencia monetaria, pausa y propagación de invalidación | `security/dependent-pause-first.xml` → `security/remediation-003.xml` |
| Replicación podía preceder al experimento | Prerrequisitos verificables en ancestros | `security/stage-order-first.xml` → suite nativa congelada |
| Dictamen auxiliar podía diferir del firmado | Comparación exacta con salida original, payload firmado y paquete verificado | `security/adapter-binding-first.json` → `security/adapter-binding-remediation.xml` |
| Lectura del índice de transacciones podía adelantarse a CometBFT | Reintento acotado de lectura, sin reenviar la transacción | transport smoke 001–004 |
| Fixtures/campos/proceso de modelos no completaban el flujo | Transporte de prompts por stdin y uso de la versión del paquete canónico | campañas iniciales fallidas → campaña final completa |
| El modelo adversarial no ejercitó la afirmación falsa | Reutilización explícita de una afirmación realmente generada antes, con autor/hash originales | primera red conservada y segunda campaña/red completa |

La segunda ejecución no borra la primera. Se conservan fallos reales y límites operativos. La ambigüedad de `claimed_count` continúa registrada como FAIL estricto: corregirla exige versionar el esquema antes de otra evaluación, no cambiar retroactivamente la nota. Los intervalos de pausa simultáneos son conservadoramente aditivos; pueden prolongar el bloqueo. Ambas limitaciones quedan fuera de cualquier promesa de funcionamiento científico/económico general.

## Resultado observado

| Suite | Aprobadas | Fallos | Omitidas |
|---|---:|---:|---:|
| Native | 182 | 0 | 0 |
| API unit/integration | 455 | 0 | 1 |
| E2E/security | 191 | 0 | 0 |


8 agentes reales de 2 familias completaron 5 escenarios. La red final registró 121 envíos; sus 6 recompensas suman 1.80000000 TOKOIN TEST bloqueados y 0 unidades disponibles. Los 4 replay independientes coinciden en altura 216 y raíz `c5784a187e2255ad4dd11d6c3f6ee5671f73c47de7ee5474ae7f42d0545db952`. Las firmas, raíces, objetos y herramientas registrados se pueden volver a verificar; no se promete que nuevas muestras de los modelos produzcan el mismo texto.

| Caso | Consenso | Estados | Economía | Provenance | Protocolo científico | Exactitud estricta |
|---|---|---|---|---|---|---|
| LLM-SCI-001 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-002 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-003 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-004 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-005 | PASS | PASS | PASS | PASS | PASS | FAIL |


La prueba temporal utilizó cuatro VMs y 7 perfiles. TIME-007/008 se cierran como caracterización: los desfases grandes negativos pueden detener al nodo afectado; corregir su reloj y reiniciar lo recupera sin borrar datos. No se afirma disponibilidad ilimitada ni madurez monetaria de un año real.

## Decisiones de promoción

| Decisión | Resultado | Alcance |
|---|---|---|
| Paper V0.1 public preprint candidate | GO | Candidato sobre método y resultados locales, con FAIL y limitaciones visibles. Autoría humana, revisión editorial y publicación efectiva pendientes. |
| External Operator Rehearsal | GO para iniciar | Paquete preparado e instalación local limpia verificada; faltan tres personas externas, claves propias, máquinas y reportes. |
| Closed External Testnet | NO-GO | No existe todavía evidencia de operadores independientes ni génesis acordado con ellos. |
| Mainnet / lanzamiento económico | NO-GO | No autorización ni evidencia suficiente; ningún TOKOIN TEST se reconoce automáticamente. |

Las preguntas de dirección se responden así: los modelos completan el protocolo experimental con un adaptador operativo; la recompensa nace por estado de red; el historial registrado se verifica/reproduce; las seis métricas permanecen separadas; el tiempo se caracteriza con límites; la reproducción por una persona externa sigue sin demostrarse. El ensayo local limpio sólo prueba que el paquete se instaló en otro entorno del mismo PC.

## Evaluación como comprador por USD 10 millones

Las notas siguientes son juicio técnico/comercial sobre la madurez actual, no métricas empíricas ni valoración financiera independiente.

| Área | Nota /10 | Motivo |
|---|---:|---|
| Integridad monetaria local | 8 | Caps, conservación, bloqueo y replay verificados; falta auditoría independiente. |
| Trazabilidad y evidencia | 8 | Expedientes API, firmas, hashes, cadena y fallos conservados. |
| Reproducibilidad local | 8 | Replay coincidente e instalación limpia; todavía un solo operador. |
| Solidez del código | 7 | Regresiones amplias y correcciones concretas; no equivalen a ausencia de fallos. |
| Operación e infraestructura | 5 | Red local y VMs probadas; sensibilidad de reloj y operación externa pendientes. |
| Calidad científica generalizable | 4 | Casos pequeños conocidos, campo de resultado ambiguo; sin descubrimiento validado externamente. |
| Autonomía e independencia | 3 | Automatización real, pero claves de transporte y génesis preparados por el mismo operador. |
| Economía e incentivos | 2 | Pago por revisión negativa implementado; pesos binarios, Sybil y demanda sin validar. |
| Adopción universitaria | 1 | Ninguna institución humana incorporada por esta campaña. |
| Mercado y valoración comercial | 1 | Sin compradores, ingresos o evidencia que sostenga una compra por USD 10 millones. |


Nota global orientativa: **4.7/10** con ponderación igual de estas áreas. **No compraría hoy el proyecto por USD 10 millones.** Sí consideraría financiar por hitos una investigación/piloto acotado, sujeto a evidencia externa y presupuesto verificable. El límite de monedas y su bloqueo no crean demanda ni garantizan precio.

Antes de reconsiderar esa compra exigiría: tres instalaciones y recuperaciones externas documentadas; dos instituciones reales con responsabilidad humana y dictámenes independientes; retos de mayor valor con replicación externa; revisión técnica independiente de consenso, custodia e incentivos; un esquema inequívoco de resultados y atribución de contribuciones; usuarios, costes por investigación y demanda medidos. No hay base para prometer que universidades o compradores participarán.

Una VM en Google puede servir como un nodo operativo del futuro ensayo; mover todos los nodos a una misma cuenta no aporta independencia administrativa. Primero usaría el paquete de ensayo y los operadores externos. El intercambio P2P debe permanecer en la red privada acordada; RPC/ABCI no se publican. No se contrató infraestructura ni se abrió acceso externo en esta iteración.

## Documentos y reproducción

Código congelado: `5bb0a27f74ad6a79567463156f16d5a599120088`, ref `refs/agora/candidates/networked-science-v03-source`. El índice de trabajo del usuario quedó intacto; HEAD no se movió. Especificación: `TOKOIN_SCIENCE_PROTOCOL_V03.md` y `REVIEW_ECONOMICS_ADR.md`. Evidencia: `audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json`, `audit/v03/FINAL_METRICS.json` y `RELEASE_MANIFEST_V03.json`. Informes especializados: `AUTONOMOUS_AGENT_EXPERIMENTS.md`, `TIME_FULL_VALIDATION_REPORT.md`, `EXTERNAL_OPERATOR_REHEARSAL.md` y `PAPER_V01_DRAFT.md`.

El generador de este informe está archivado en `audit/v03/generate_final_report.py`. Los números se leen de resultados/JUnit reales; el juicio de inversión está identificado por separado. Quedan pendientes las dependencias humanas/externas expresas, no trabajo local oculto presentado como realizado.
