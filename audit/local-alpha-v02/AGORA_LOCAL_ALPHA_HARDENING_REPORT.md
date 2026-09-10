# AGORA / TOKOIN — resultados de hardening local V0.2

**Dos iteraciones implementadas y verificadas en este PC.** Cierre del 9 de septiembre de 2026 (México). La cobertura del plan sigue parcialmente abierta; no es autorización de publicación ni lanzamiento económico.

## Executive Summary

Se implementaron y probaron dos iteraciones en este PC. La primera reprodujo defectos y produjo [RESULTS.md](iteration-1/RESULTS.md). La segunda se derivó de ese documento mediante un [plan enlazado por SHA-256](iteration-2/PLAN.md). Los fallos iniciales y las campañas parciales se conservaron.

El resultado es una alpha local más verificable: firmas ligadas a génesis, tiempo de protocolo explícito, persistencia comprobada ante fallos, wallet cifrada operable, pruebas monetarias extensas y expedientes científicos enlazados con recompensas TEST. No se modificaron saldos vivos, no se migró la base operativa y no se publicó ningún servicio.

## Baseline Commit and Hashes

- Baseline: `569e4ca2b28a4dd90dfe3b5cdf342451477248c8`.
- Entrega final: `aa21f2e6fac27362da1017ca5800a1ded1bdb7bf`.
- Validación nativa congelada: `c37419e216ce181831546e0d251674de3f8e5d4b`; el árbol nativo es idéntico en ambos commits. La última corrección sólo modifica fixtures de integración y su documento.
- La rama activa y el índice del usuario se conservaron; las congelaciones usan referencias separadas.
- Motor: CometBFT 0.38.26, commit `94d77f9f51a72e2b7d832798859f6222f08028f8`.
- SHA-256 del motor: `6edb2aa0f223e71758a48cf3d13d9d7ffd26f3357585bebe54311ba71f11ac3f`.

Una recompilación con fuentes extraídas de nuevo y caché Go nueva produjo el mismo binario. Se reutilizaron descargas verificadas y el mismo PC. Los auxiliares de fallos también se recompilaron en dos rutas distintas con hashes iguales. Esto no es una atestación de terceros.

## Architecture Changes

El sobre TX V3 vincula protocolo, cadena, génesis, emisor, nonce, tipo y contenido. `ProtocolTime` y `unlock_at` hacen explícita la maduración. El journal incluye cabeza durable y hashes de estado anterior/siguiente. La apelación se limita a una reapertura con evidencia nueva y resolución firmada para su revisión. Repetir evidencia cambiando el método ya no permite eludir la detección de duplicados.

La invalidación científica posterior conserva balances y transferencias. El reparto utiliza enteros y residuos deterministas. Se añadieron wallet cifrada, CLI offline, evidencias verificables y un proveedor `python-scripted-test` declarado correctamente. No se cambió el motor BFT ni el reparto 10/10/51/20/9.

## Consensus Time Audit

El inventario revisa código propio y el control AST prohíbe dependencias de reloj/dinámica en el núcleo puro. El adaptador toma el timestamp consensuado; el journal lo conserva. AGORA mantiene relojes de servidor para coordinar ciencia, separados de la maduración monetaria soberana.

Se probaron el instante anterior, igual y posterior al vencimiento, retrocesos, saltos, pausa, reanudación y reinicio. Los votos con timestamps ±60 segundos probaron una clase de fallos temporales en red. **No equivalen a desplazar el reloj completo de un validador**: TIME-007/008 conservan cobertura parcial. El reloj del host no se alteró. Véase `docs/native/TOKOIN_TIME_SEMANTICS.md`.

## Transaction and Nonce Audit

Se rechazan replay, firmas reutilizadas entre cadenas o génesis, modificaciones del contenido/tipo/emisor/versión, serializaciones alternativas y entradas fuera de límites. Una prueba envió 128 consultas concurrentes con el mismo nonce: `CheckTx` es preliminar y no reserva nonces; `PrepareProposal` selecciona una transacción y `Commit` la aplica una vez.

El corpus de fuzz contiene 2,012 entradas inválidas, incluida profundidad excesiva. El estado comprometido permanece intacto. No se interpreta una respuesta preliminar como asentamiento definitivo.

## Determinism Results

Los journals se reconstruyen desde génesis. La red compara block hash y AppHash a la misma altura, evitando comparar estados latest de alturas diferentes. Los snapshots ABCI se rechazan; la sincronización soportada reproduce bloques desde génesis, incluida una aplicación nueva sin historial.

La reconstrucción en una copia limpia del repositorio y un entorno Python nuevo se registra aparte. Sigue siendo el mismo PC, no una máquina administrada por un tercero.

## Byzantine Test Results

La campaña contempla progreso 4/4 y 3/4, detención 2/4, particiones 3+1 y 2+2, recuperación, muerte del productor durante `PrepareProposal`, rechazo de una propuesta inválida y doble firma con evidencia aceptada e incluida en un bloque.

También contempla votos retrasados, fallos repetidos de propuesta, latencia, cortes TCP, un nodo atrasado más de 220 bloques y sincronización de un nodo nuevo. Una campaña adicional usa `tc netem` dentro de namespaces efímeros para pérdida y reordenamiento real de paquetes, sin cambiar la red del host.

Los informes conservan el alcance de cada campaña. Cuatro procesos de este PC no demuestran independencia física ni administrativa. No se afirma seguridad con dos de cuatro validadores maliciosos.

## Crash Recovery Results

Se terminaron procesos realmente en los límites ABCI, finalización, persistencia, fsync y commit, y durante el procesamiento de transacciones. Las pruebas de `SQLITE_FULL` y `query_only` verifican que el estado provisional no se promueve cuando falla la escritura y que puede recuperarse después.

Se detectan truncamiento, alteración y duplicación de entradas. No se demuestra supervivencia a pérdida física de todo el disco. Tampoco se atribuye al journal resistencia frente a un atacante que reemplaza a la vez la base y todas las referencias externas de confianza: siguen siendo necesarias las firmas BFT y un génesis confiable.

## Wallet Security Results

La wallet utiliza AES-256-GCM y scrypt, vincula cadena/génesis mediante datos autenticados, incluye checksum/versión, exige permisos 0600 y rechaza enlaces simbólicos. Backup y restauración verifican el contenedor.

La CLI recibe la contraseña por `getpass`, rechaza fallback con eco, presenta cadena/dirección/nonce/destino/importe y escribe una transacción firmada offline sin enviarla. Se corrigieron doble lectura del backup, JSON duplicado, errores que reflejaban argumentos y un `RecursionError` ante JSON profundo. La API PKCS8 anterior permanece para compatibilidad; el flujo operativo nuevo es `wallet_cli`.

## Monetary Invariant Results

Cada campaña ejecuta 100,000 secuencias: 400,000 transiciones firmadas, 200,000 aceptadas y 200,000 rechazos esperados. Se contrastan balances y distribución con una referencia entera y se prueban capacidad y exceso por una unidad. La semilla es `20260909`; las repeticiones reproducen el mismo corpus, **no son casos independientes adicionales**.

Se mantienen máximo de 1,000,000 TOKOIN, cap TEST de 500, ocho decimales y cero premine. La revocación no recupera capacidad de emisión ya consumida. Se prueban unidades mínimas, importes 17/99, residuos y gasto bloqueado. El reward positivo TEST sigue fijado en un TOKOIN; no se rediseñó la política económica.

## Scientific E2E Results

SCI-001 a SCI-006 recorren API y base aislada con cuatro trabajadores Python por caso, revisiones ciegas con commit/reveal, genealogía y paquete canónico. Dos casos aptos autorizan un TOKOIN TEST en génesis separados; cuatro casos negativos rechazan emisión. SCI-002 admite y resuelve una impugnación; después se prueba maduración simulada y transferencia. Cada secuencia admite replay exacto.

El puente termina en la aplicación nativa: **no ejecuta un año por red ni representa universidades o agentes LLM autónomos**. Las 25 regresiones API y una prueba de downgrade/upgrade de la migración 0038 se ejecutaron en bases aisladas; Codex/Claude permanecen compatibles.

## Adversarial Scientific Results

Se comprobaron duplicado exacto rechazado, voto propio rechazado, voto repetido idempotente, contradicciones conservadas, evidencia fabricada señalada, replicación fallida, resultado inconcluso y revisión negativa. Las señales de similitud y dueño común son `REVIEW_ONLY`, sin condena ni penalización automática.

No están resueltos plagio semántico general, citas falsas en dominios arbitrarios, identidades Sybil, colusión oculta o censura de admisión. El recibo de una revisión negativa conserva trabajo, pero **no equivale a una compensación monetaria independiente de la aprobación**.

## Failures Found

Defectos de implementación: replay entre génesis distintos; truncamiento final del journal aceptado; proveedor Python incompatible con VARCHAR/CHECK; JSON profundo en CLI; doble lectura del backup; auxiliares Go dependientes de la ruta de compilación.

Defectos del arnés: formato UTC, reconexión del signer tras reinicio, plazo insuficiente para sincronización y un constructor de fuzz que intentaba canonizar un float antes de enviarlo. Estos últimos no se presentan como fallos del consenso. La suite API completa descubrió además dos fallos de aislamiento entre tests: datos científicos persistentes y una migración que asumía tablas vacías. Se corrigieron con rollback transaccional y una sub-base propia, preservando las aserciones originales.

## Failures Fixed

Firmas V3, cabeza durable atómica, migración 0038 explícita, errores CLI controlados, lectura única de backup autenticada y builds portables corrigieron los defectos anteriores. Las regresiones y los resultados antes/después se conservan. La suite amplia pasó de 599 PASS/2 FAIL a 601 PASS, sin exclusiones; no quedaron sub-bases temporales de migración. El fuzz corregido pasó sin relajar el protocolo.

## Failures Remaining

No se observó un bypass monetario ni divergencia comprometida en los escenarios aprobados. El alcance solicitado todavía tiene límites: desplazamiento del reloj completo, ciclo científico integral por red, agentes LLM autónomos en esta campaña y compensación independiente de revisión negativa.

La revisión por universidades reales, operadores externos, auditoría independiente y decisiones de divulgación requieren participantes o decisiones fuera de este laboratorio. No se convierten en PASS mediante simulación. El detalle se encuentra en la matriz de requisitos.

## Security Limitations

Escasez no demuestra demanda ni valor. Las claves TEST derivadas de semillas públicas jamás deben utilizarse con fondos. El registro institucional del laboratorio es declarativo, no una acreditación humana. No hay admisión permissionless ni política anticensura completa.

La invalidación posterior informa sin confiscación; su economía de producción está pendiente. Veinte transacciones secuenciales miden ese ensayo, no capacidad sostenida. Los escaneos de secretos y dependencias documentan su alcance y fecha, no ausencia universal de vulnerabilidades.

## Evidence Pack Index

Consultar `EVIDENCE_INDEX.json`, `RELEASE_MANIFEST.json`, `REQUIREMENTS_MATRIX.md` y los directorios de cada campaña. Las ejecuciones de desarrollo con HEAD y hashes de archivos se distinguen del candidato congelado. Un índice hash no es una auditoría humana.

## Exact Reproduction Instructions

Usar el commit congelado y las instrucciones de [REPRODUCE.md](REPRODUCE.md). Instalar dependencias fijadas, ejecutar tests nativos con `AGORA_ENV=test` y pruebas de API únicamente con `scripts/run-isolated-tests.sh`. Construir motor y auxiliares verificando hashes; ejecutar fallos sólo en red TEST aislada. Los datos vivos no son fixtures.

## GO or NO-GO recommendation for publication candidate

**GO para redactar y revisar internamente un informe metodológico acotado. NO-GO para afirmar cumplimiento del 100% del master o publicar el sistema como validado científica y económicamente.** Quedan cobertura completa, revisión externa, related work, autoría y decisión de divulgación. No se envió un paper.

## GO or NO-GO recommendation for closed external testnet

**NO-GO como invitación operativa inmediata.** Se prepararon ocho guías y un manifest; terceros deben validar instalación, claves propias, máquinas separadas y pruebas de recuperación/sincronización/partición. Mainnet y lanzamiento de moneda con valor permanecen NO-GO.

## Valoración como comprador hipotético

Notas subjetivas de ingeniería, de 0 a 10; no son una valoración financiera ni una predicción.

| Área | Nota | Condición pendiente |
|---|---:|---|
| Arquitectura y separación ciencia/dinero | 7 | Integración completa de producto |
| Integridad monetaria local | 8 | Auditoría independiente |
| Recuperación y operación | 7 | Máquinas y operadores externos |
| Protocolo científico | 5 | Revisión humana y ensayos realistas con LLM |
| Economía e incentivos | 3 | Demanda, costes y revisión negativa |
| Descentralización real | 2 | Admisión y operadores independientes |
| Preparación para lanzamiento con valor | 2 | Evidencia de testnet y controles externos |

**Calificación global subjetiva: 5/10. No comprometería 10 millones de USD hoy.** Consideraría financiación de investigación por hitos, acotada y cancelable: auditoría, operadores independientes, replicación científica real, financiación de nodos/revisiones y utilidad demostrada sin depender de especulación. La idea merece experimentación; estos resultados no justifican todavía el valor de compra propuesto.

## Resultados consolidados del candidato

| Verificación | Resultado observado | Evidencia |
|---|---|---|
| Suite nativa en copia limpia y entorno nuevo | 123 passed in 5.30s | iteration-2/clean-clone-tests.txt |
| Suite API completa corregida | 601 passed in 68.51s | iteration-2/api-suite-full-corrected.txt |
| Primera suite API completa | 2 failed, 599 passed; preservada | iteration-2/api-suite-full.txt |
| Último replay monetario | 100,000 secuencias, 400,000 transiciones, 0 errores, 139.913s | monetary/final-candidate-100k/results.json |
| Consenso y red | 15 BFT cubiertos entre dos campañas congeladas | chaos-frozen/summary.json |
| Comparación de cuatro validadores | 483 alturas coincidentes | chaos-frozen/20260910T031559Z-9342b265/report.json |
| Pérdida IP y recuperación | 194 paquetes descartados por netem | chaos-frozen/20260910T031634Z-e58a5c99/report.json |
| Journals reproducidos | 5 de campaña completa y 4 de netem | independent-journal-replays.json en cada run |
| Build y auxiliares | Hashes repetibles localmente | iteration-2/clean-build-result.json y chaos/helper-reproducibility.json |
| Análisis estático | Ruff PASS; mypy 11 archivos sin errores | iteration-2/clean-clone-lint.txt y mypy-final.txt |
| Dependencias nativas | Sin vulnerabilidades conocidas reportadas en el escaneo | iteration-2/dependency-audit.json |
| Correspondencia de fuente | 381 archivos comprobados; 0 diferencias | iteration-2/source-equivalence.json |
| Servicio operativo, consulta final | HTTP 200; PostgreSQL/Redis OK | final-local-status.json |

La carga de 20 transacciones secuenciales midió 1.51126 tx/s; no es una capacidad sostenida ni un benchmark de producción. Todos los procesos creados por las campañas de red terminaron. La API viva sigue con su versión operativa previa: las modificaciones se probaron aisladamente y no se promovieron a producción.
