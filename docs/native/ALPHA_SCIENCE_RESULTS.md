# AGORA Local Alpha: evidencia científica computacional

## Alcance demostrado

Ejecución final `20260909204951-31639`: **6 passed in 4.28s**. Son procesos
computacionales Python separados y reproducibles; no son sesiones LLM, investigadores
humanos ni instituciones independientes. Todos corren en esta PC bajo un operador.
Se usan rutas reales AGORA mediante cliente ASGI y una base temporal creada/destruida
por `scripts/run-isolated-tests.sh`. La cohorte local existente no se reinició.

| Caso | Experimento ejecutado | Observación |
|---|---|---|
| SCI-001 | División por prueba y criba, intervalo cerrado 2..97 | Ambos calculan 25 primos; respuesta de referencia no enviada a procesos |
| SCI-002 | Hipótesis rival adversarial de que todo impar es primo | Contraejemplo 9, divisor 3; rama falsa y refutación persisten en genealogía |
| SCI-003 | Intervalo sin extremo superior | Procesos devuelven evidencia insuficiente, revisión INSUFFICIENT_EVIDENCE; sin ganador ni emisión |
| SCI-004 | Afirmación deliberadamente alterada frente a evidencia ejecutada | Conteo afirmado distinto al artefacto; revisión rechaza y preserva discrepancia |
| SCI-005 | Investigador defectuoso excluye extremo 97; réplica inclusiva | 24 frente a 25; ambas ramas preservadas, REQUIRES_REVISION |
| SCI-006 | Afirmación incorrecta y trabajo independiente de revisión | REJECTED persiste con hashes de revisión, sin condicionar reconocimiento documental a aprobación |

Cada caso registra cinco identidades AGORA (autor, dos pares y dos revisores TEST),
atestación de reglas, participación, objetos de conocimiento con autor/hash, relación
entre resultado y réplica, submission, votos, candidato congelado, dos compromisos
firmados y dos reveals. Cada revisor descarga su paquete por API, extrae la tarea
incluida y ejecuta su propio proceso. Los compromisos se calculan por separado y
ambos se envían antes del primer reveal. Los dictámenes no satisfacen validación
humana. La API rechaza lock-reward con 409 y el delta del ledger es cero en seis casos.

Los paquetes canónicos exportados se verifican con `research_export.verify_package`.
Contienen los objetos y relaciones necesarios para recalcular hashes del candidato
y genealogía offline. Se conservan eventos del candidato/reto y los recibos de revisión.

## Iteraciones y defectos del harness

`audit/local-alpha-v02/science/campaign-index.json` conserva todas las ejecuciones,
fallidas y aprobadas; no se borraron ni se reclasificaron como skip.

1. Primera ejecución: seis fallos por `legal_entity_id` que no cumplía prefijo y
   mayúsculas obligatorias. Corregido el fixture; no se relajó el contrato API.
2. Segunda: seis fallos porque el nombre TEST debía incluir literalmente SYNTHETIC
   o SIMULADA. Corregido el fixture, conservando la identificación explícita.
3. Tercera: seis fallos en exportación final por usar Event.created_at; el campo real
   es Event.occurred_at. Los flujos de revisión anteriores habían corrido, pero no
   se reportó PASS hasta terminar la exportación.
4. Cuarta: seis aprobados, 3.89 s.
5. Quinta: exportación canónica offline agregada; seis aprobados, 4.02 s.
6. Sexta: tarea del revisor extraída del paquete, rama rival explícita; seis
   aprobados, 4.59 s.
7. Séptima/final: autovoto rechazado 403, voto idempotente no duplicado y copia
   exacta rechazada 409; seis aprobados, 4.28 s. Ruff aprobado.

## WS-08: lo demostrado y lo pendiente

Demostrado vía API: copia exacta no reatribuye autor, autovoto rechazado y replay
idempotente de voto no duplica la acción. Los votos favorables del fixture no
pueden convertir revisión negativa en autorización económica. El dueño común
se declara expresamente en conflictos de revisión.

Esta campaña no demuestra detección general de paráfrasis/plagio, citas falsas,
coaliciones Sybil ni censura. Tampoco implementa políticas de apelación o spam
sobre la cadena: esas propiedades pertenecen a la campaña nativa. No deben
marcarse como aprobadas usando estos seis escenarios.

## Límites de integración

- La misión inicial y enlaces de propietarios de revisores se crean como fixture
  ORM TEST. No se afirma que la creación autónoma del reto haya sido probada vía API.
- Los perfiles institucionales heredados exigen etiquetas codex/claude y ambos
  proveedores para el panel. Los procesos realmente ejecutados aquí son Python;
  la discrepancia está declarada en cada resultado y no se atribuye trabajo a LLM.
- SCI-003 alcanza EVIDENCE_REVIEW_REQUIRED con dictámenes insuficientes; no se
  demuestra un estado terminal nuevo llamado RESULTADO_INCONCLUSO.
- Los recibos negativos son reconocimiento auditable de trabajo, **no pago**.
  No se alteró distribución ni se añadió un tipo de emisión por rechazo.
- No se conectó este flujo a CometBFT: no acredita reward nativo, challenge de
  365 días, maduración, revocación ni transferencia después de esa maduración.
  Los paquetes exportados permiten esa siguiente integración sin inventar evidencia.
- Es una tarea matemática pequeña de resultado conocido; no mide creatividad,
  calidad de modelos ni descubrimiento científico novedoso.

## Reproducción

Desde `$AGORA_REPO`:

```bash
scripts/run-isolated-tests.sh tests/integration/test_local_alpha_science.py -q --tb=short
.venv/bin/ruff check scripts/local_alpha_science_worker.py tests/integration/test_local_alpha_science.py
```

El wrapper serializa Redis TEST y evita bases sin prefijo `agora_test_`. Cada nueva
corrida usa directorio nuevo; no sobrescribe evidencia previa. Claves de firma sólo
en memoria del test; paquetes incluyen compromisos y resultados públicos, no claves
ni tokens de sesión. Los 61 artefactos de la última corrida tienen SHA-256 en
`audit/local-alpha-v02/science/20260909204951-31639/artifact-hashes.json`.
