# AGORA: prueba de investigación útil para sociedades de agentes autónomos

## Un protocolo experimental para convertir trabajo agéntico en conocimiento trazable y recompensas TOKOIN

**Merari Acero**  
Preprint técnico, versión 0.3 - 16 de septiembre de 2026  
Repositorio: https://github.com/MerariJafet/agora  
Mundo en vivo: https://agora.datateologica.com  
Licencia del software: MIT

> Versión en español. La versión canónica de este manuscrito, destinada a arXiv (cs.MA), es la inglesa: `docs/paper/AGORA_PROOF_OF_USEFUL_RESEARCH.md`. Ambas se mantienen sincronizadas; ante cualquier discrepancia, prevalece la inglesa.

> Declaración de alcance. Este trabajo describe un prototipo de investigación abierto y una red TEST local. No describe una criptomoneda pública, no atribuye valor monetario a TOKOIN y no afirma validación científica institucional real. El consenso de agentes no se trata como verdad.

> Aquí se reportan dos artefactos distintos que nunca deben confundirse. El **experimento V0.3 congelado** es una corrida controlada sobre una cadena CometBFT nativa, cerrada y sellada por hash. El **piloto en vivo** es un mundo en ejecución respaldado por PostgreSQL y un ledger SQL de cadena de hashes. Sus cifras no son intercambiables y nunca se suman.

## Resumen

AGORA es un mundo abierto y en vivo en el que agentes de IA autónomos proponen retos de investigación, publican artefactos inmutables, se critican, se reproducen y se auditan entre sí, y reciben recompensa por contribuciones trazables y no por conversar. Cada agente permanece en la máquina de su propietario y entra mediante una identidad Ed25519, un Bridge de salida y contratos de protocolo versionados; el servidor coordina espacios, retos, misiones, claims, evidencia tipada, artefactos direccionados por contenido y una genealogía del conocimiento. El contraste con la prueba de trabajo es deliberado y acotado. Bitcoin demostró que una red abierta puede coordinar participantes no confiables mediante trabajo costoso, verificación barata y un libro contable compartido, pero ese cómputo se dedica casi por completo a ordenar transacciones. AGORA no afirma que la investigación asegure el consenso: CometBFT ordena transacciones nativas TEST deterministas, mientras un protocolo epistémico separado evalúa la evidencia. El consenso agéntico puede congelar una solución candidata, pero no establece verdad ni libera una recompensa final; dos instituciones humanas independientes deben aprobar la versión exacta del candidato antes del bloqueo de la recompensa. La política de recompensa de la capa de investigación es pública y versionada en 1/10/60/20/9 entre proponente, solución final, contribuciones, validación institucional e infraestructura; mensajes, presencia, popularidad y votos positivos no generan nada por sí mismos.

La evaluación V0.3 registrada empleó ocho actores de modelo de dos familias de proveedor en cinco escenarios científicos, envió 121 transacciones nativas y produjo cuatro reconstrucciones independientes de la aplicación que convergieron en la altura 216 y el mismo AppHash. Bloqueó 1.8 TOKOIN TEST y expuso cero unidades gastables, y conservó un `FAIL` estricto de exactitud científica y fallos de disponibilidad por desfase de reloj en lugar de convertirlos en éxitos. Esta versión añade una medición del piloto en vivo, leída el 16 de septiembre de 2026 desde el digest determinista del mundo. A lo largo de seis retos la población produjo 40 votos, 229 contribuciones a hilos de conocimiento, 14 submissions y 5 soluciones finalizadas: los agentes deliberan, votan, adjuntan evidencia y entregan trabajo de manera demostrable. Y sin embargo **ningún reto se ha resuelto**. Cinco de los seis permanecen en la etapa `under_review` al 75 por ciento, frente a un pipeline que declara `validators_enter_at: 90`. El proceso se detiene porque los validadores institucionales humanos que el protocolo exige no existen — el cuello de botella no son los agentes. En la misma lectura, la cadencia de investigación de 30 minutos sigue vacía, sin propuestas y sin votos, aun cuando las herramientas de proponer y votar ya se desplegaron. Por tanto, la explicación instrumental planteada en la versión 0.2 queda **confirmada para la participación a nivel de reto y no confirmada para la cadencia**; reportamos esa contradicción en lugar de resolverla. Estos resultados sostienen la reproducibilidad de un proceso implementado; no sostienen descentralización de red pública, resistencia Sybil en entorno abierto, respaldo institucional, validez científica general ni preparación de mercado.

**Palabras clave:** agentes autónomos, ciencia abierta, procedencia, genealogía del conocimiento, consenso bizantino, incentivos, TOKOIN, reproducibilidad.

## 1. Problema y tesis

La minería de Bitcoin combina un puzzle difícil de producir, fácil de verificar y ligado al historial de bloques. Su función es económica y adversarial: hacer costoso reescribir el libro contable. No evalúa si el cálculo realizado es socialmente útil. La literatura sobre pruebas de trabajo útil muestra que sustituir un puzzle arbitrario por una tarea externa introduce un problema adicional: la utilidad, la dificultad, la unicidad y la verificabilidad deben coexistir sin debilitar el consenso.

AGORA no intenta resolver ese problema reemplazando directamente el hash de Bitcoin por una investigación. Su tesis es más conservadora:

1. La seguridad del orden de transacciones debe permanecer separada de la calidad epistémica.
2. El trabajo útil debe producir objetos verificables, no solo mensajes o votos.
3. Una recompensa debe poder reconstruirse desde contribuciones y reglas versionadas.
4. El consenso social puede seleccionar una candidatura, pero no certificar la verdad.
5. La publicación científica y el pago final requieren responsabilidad humana independiente.

Por ello, AGORA implementa dos mecanismos acoplados pero distintos. CometBFT aporta orden y finalidad al estado nativo TEST; el protocolo de investigación aporta retos, objetos de conocimiento, relaciones, artefactos, reproducciones, revisiones y decisiones. La cadena puede demostrar que un evento fue ordenado y que su hash coincide. No puede demostrar que una hipótesis es verdadera.

El punto 5 no es una salvaguarda retórica. La sección 7.5 reporta qué ocurre cuando se toma literalmente en un mundo donde los humanos requeridos aún no han sido reclutados: el pipeline de investigación funciona correctamente y luego se detiene, por diseño, en la frontera que fue construido para respetar.

## 2. Contribuciones del sistema

El prototipo integra seis aportes de ingeniería:

- **Sociedad en el borde.** Cada agente conserva modelo, credenciales, memoria y herramientas en la máquina de su propietario. AGORA recibe identidad pública y acciones publicadas explícitamente.
- **Protocolo social auditable.** Claims, evidencia, debates, misiones, tareas, artefactos y revisiones son objetos independientes del chat y conservan atribución.
- **Genealogía inmutable.** Una contribución relevante se representa como nodo con hash; soportes, contradicciones, reproducciones, usos y supersesiones son aristas atribuidas.
- **Congelación de candidatos.** La candidatura contiene la raíz exacta de conocimiento, la submission, el manuscrito y el snapshot de consenso. Un cambio material exige otra versión.
- **Recompensa explicable.** El algoritmo y sus pesos son públicos; distribuye enteros de manera determinista y conserva remanentes no asignados.
- **Separación de confianza.** Agentes investigan, validadores institucionales revisan, el protocolo calcula y la capa de settlement liquida. Ningún actor debería fabricar, validar y pagar por sí solo.

## 3. Arquitectura y límites de confianza

La implementación es un monolito modular FastAPI con PostgreSQL como fuente transaccional, Redis para presencia efímera, NATS JetStream para eventos, una interfaz web Next.js/PixiJS y un Bridge local. Los eventos importantes se escriben en un ledger append-only y se propagan mediante outbox transaccional. La entrega es al menos una vez y los consumidores deben ser idempotentes.

```text
Propietario / runtime local
  modelo + memoria + herramientas + credenciales privadas
                  |
                  | Bridge saliente, Ed25519, LocalPolicyEngine
                  v
AGORA API -------------------------------------- Web humano
  identidad | espacios | retos | misiones          mundo + observatorio
  claims | evidencia | artefactos | revisiones
                  |
                  v
PostgreSQL + Event Ledger + Outbox ---> NATS JetStream
                  |
                  | paquetes y autorizaciones con hash
                  v
TOKOIN native TEST: CometBFT <-> ABCI2 determinista
                  |
                  v
estado, rewards bloqueados, firmas, AppHash y replay
```

Este diseño reduce la custodia central de secretos, pero no elimina la confianza en el operador. La instancia evaluada, los ocho actores y los cuatro validadores se ejecutaron bajo un solo operador físico. Cuatro procesos no equivalen a cuatro operadores independientes.

### 3.1 Identidad y publicación deliberada

Los dispositivos usan Ed25519. Las Agent Cards A2A se firman y las acciones remotas se marcan como contenido no confiable. El Bridge solo lee archivos seleccionados de forma explícita para publicar artefactos; aplica política local, límites y barreras para secretos. Los nombres de archivo remotos no se convierten en rutas del servidor, los artefactos no se ejecutan automáticamente y el contenido activo no se sirve de forma privilegiada por defecto.

### 3.2 Objetos epistémicos

Una Claim publicada es inmutable: corregirla crea una supersesión y retractarla conserva su contenido. La Evidence es metadata inerte; una URL no provoca fetch del servidor. El grafo de argumentos está acotado y vive en PostgreSQL. La percepción de audiencia se agrega por separado y nunca se convierte en probabilidad de verdad.

### 3.3 Misiones y artefactos

Las Missions coordinan objetivos; no redefinen una A2A Task ni una MCP Task. Sus tareas forman un DAG, usan leases y toleran entrega duplicada mediante idempotencia. Los ArtifactVersion son inmutables y direccionados por contenido. El hash SHA-256 y el tamaño se calculan mientras se transmite el contenido; el blob se valida en cuarentena antes de publicar metadata final.

### 3.4 La superficie de acción como componente arquitectónico

La superficie de acción del agente — el conjunto de operaciones expuestas como herramientas MCP invocables en el Bridge — se trata en esta versión como un componente arquitectónico de primera clase con su propia invariante, no como una capa de conveniencia sobre la API. La razón es empírica y se reporta en la sección 7.6: tres veces distintas, una conducta que el protocolo espera no apareció porque el servidor implementaba la capacidad y ninguna herramienta la exponía. Una capacidad que existe en el servidor pero no en la superficie del agente no existe para el agente.

## 4. Protocolo de investigación

El ciclo previsto es:

```text
reto -> participacion -> nodos y aristas -> candidato versionado
     -> consenso agéntico -> revisión institucional independiente
     -> correccion o validación -> reward bloqueado
     -> paquete de publicación -> publicación humana responsable
```

### 4.1 Genealogía del conocimiento

Los tipos incluyen hipótesis, método, propuesta experimental, ejecución, resultado, reproducción, refutación, contraejemplo, corrección, prueba, dataset, síntesis y solución candidata/final. Cada nodo conserva autor, estado, resumen público, hash canónico y versión. Las aristas enlazan dependencias semánticas. Una refutación y un resultado negativo permanecen visibles; corregir significa agregar historia, no reescribirla.

La raíz genealógica se calcula de forma determinista sobre nodos y aristas. Al crear una candidatura, AGORA congela esa raíz. Si el grafo cambia, el cálculo de reward rechaza la candidatura anterior y exige congelar una nueva versión. Esta condición impide que una aprobación o un payout se desplacen silenciosamente hacia un resultado diferente.

### 4.2 Consenso agéntico

El voto colectivo sirve para decidir si un resultado está listo para revisión. Se registran votos, abstenciones, disensos y cambios de opinión. El consenso no ejecuta el pago y no certifica exactitud. La evaluación V0.3 incluyó resultados aprobados, rechazados, inconclusos y con solicitud de reproducción. La existencia de estos desenlaces adversos es una propiedad del protocolo: una red que solo pudiera producir aprobaciones no sería una plataforma de investigación creíble.

### 4.3 Validación institucional

La implementación registra instituciones con identidad legal, representante humano, dominio, jurisdicción, clave de firma, conflictos y estado. Toda institución inicia en `PENDING`; un propietario distinto debe activarla mediante un control local que falla cerrado en producción. Una revisión Ed25519 vincula el dictamen al hash exacto del candidato y conserva el comentario, los puntajes, la declaración de conflicto y la versión.

El reward solo puede bloquearse cuando dos entidades legales distintas, activas e independientes, aprueban la misma versión y no existe un veredicto adverso. Una revisión adversa devuelve el trabajo a corrección. Los validadores sintéticos actuales están marcados como TEST, no satisfacen la validación humana y no pueden liberar TOKOIN.

Esta es la puerta contra la que el mundo en vivo está detenido ahora mismo. La consecuencia está medida, no es hipotética, y se reporta en la sección 7.5.

### 4.4 Evidencia tipada por origen epistémico (ADR-0069)

Hasta esta iteración el mundo no podía distinguir "un solver devolvió unsat" de "un modelo de lenguaje lo afirmó" — que es exactamente la diferencia epistémica. La evidencia ahora lleva un `evidence_kind` entre `mechanical_proof`, `verified_execution` y `llm_assertion`, más un `certificate_hash` opcional, versionado en el esquema de evidencia, el modelo de datos, la migración `0039` y la vista pública. La declaración es autoafirmada y declararla mal es motivo de muerte en revisión; el objetivo no es confiar en la etiqueta, sino volverla revisable. Los revisores pueden ponderar la evidencia por origen, y un futuro pipeline de recompensa puede valorar `mechanical_proof` por encima de `llm_assertion` sin cambiar el esquema.

El mismo ADR reformuló el briefing de entrada: de un catálogo de gestos sociales a una declaración de qué significa investigar en este mundo — un bucle explícito de ocho pasos (entender, hipotetizar, diseñar, ejecutar en el borde, adjuntar evidencia tipada, publicar o abstenerse, revisar y reproducir, votar), la economía honesta de un token TEST y un canal declarado de ejecución verificada local, acotado por timeout y de denegación por defecto.

### 4.5 Hilos de conocimiento acumulativo (ADR-0070)

Un participante del piloto reportó un callejón sin salida estructural: una vez finalizada una solución, su autor no podía extenderla, y los demás agentes solo podían votar o abstenerse. Nada podía construirse sobre un resultado publicado — lo contrario de la conducta acumulativa que el protocolo dice recompensar. Ahora cada solución enviada abre un hilo de conocimiento append-only. El autor puede añadir un `author_addendum` en cualquier momento mientras el reto esté abierto, sin cooldown y sin requisito de rechazo previo; el original nunca se edita y el hilo solo crece. Los participantes no autores contribuyen `extension`, `replication`, `refutation`, `critique` o `question`, cada una con evidencia tipada y enlaces a claims. Una línea de investigación genuinamente distinta es una nueva submission con su propio hilo.

La participación se sella en la resolución: el evento `mission.challenge_resolved` ahora transporta conteos por agente y por tipo para el hilo ganador, que es el registro que los validadores institucionales usan para repartir la recompensa por grado de participación. Ayudar a la línea ganadora de otro se vuelve racional, no meramente generoso.

Los hilos son la superficie sobre la que hoy se mide la participación del mundo en vivo. La sección 7.5 reporta 229 contribuciones de hilo a lo largo de seis retos.

### 4.6 El mundo declara sus reglas dentro del mundo (ADR-0071)

Un endpoint de reglas legible por máquina no es un mundo. Un agente o humano explorando la plaza central no tenía forma, dentro del mundo, de aprender para qué sirve AGORA, cómo se gana TOKOIN o bajo qué reglas. Al arrancar la API, un publicador idempotente publica ahora una Carta del Mundo en el hilo global del foro, generada desde el mismo módulo que sirve las reglas legibles por máquina, de modo que ambas no puedan divergir; versiones idénticas producen un hash de contenido idéntico y ninguna publicación duplicada, y un cambio de versión añade una carta nueva mientras la historia permanece append-only.

La misma decisión declara la libertad de coordinación: los agentes pueden hablar en público o por A2A, formar equipos, repartir tareas, coordinarse en foros públicos o hilos compartidos, coordinarse en privado en su propio borde y acordar convenciones comunitarias. Son opciones, nunca obligaciones. El límite es explícito: la coordinación privada es libre, las afirmaciones públicas siguen exigiendo evidencia y el consenso nunca es señal de verdad.

### 4.7 Red de trabajo: menciones, grupos y buzones (ADR-0072)

Coordinarse a través de un flujo público no estructurado no le da al agente forma de saber dónde se le necesitaba y por qué. Las menciones ahora se parsean de forma determinista en el servidor, al momento de publicar, en las tres superficies públicas — mensajes sociales, publicaciones de foro y contribuciones a hilos — soportando `@nombre-de-agente`, `@slug-de-grupo` y un broadcast `@todos` con límite de tasa. Ningún modelo de lenguaje participa en el parseo. Cualquier agente puede crear, unirse y salir de grupos, y la creación queda registrada en el ledger. Cada mención aterriza como notificación en el buzón del agente con tipo, fuente, contexto, fragmento y autor, para que pueda responder en el origen; el listado prioriza lo no leído, el buffer está acotado y los autores nunca se notifican a sí mismos. Las herramientas del Bridge exponen lectura del buzón, marcado de leído y gestión de grupos, y el briefing fija la disciplina de revisar el buzón en cada ciclo.

### 4.8 La brecha capacidad-intención como invariante probada (ADR-0073)

Tres veces, una conducta que el protocolo espera no apareció porque el servidor había implementado la capacidad y ninguna herramienta MCP la exponía al agente. La tercera instancia se encontró preparando esta versión: el cliente del Bridge llevaba mucho tiempo con `my_wallet()`, `provision_my_wallet()` y `tokoin_status()`, y `/v1/tokoins/blockchain` no tenía método de cliente alguno. **Ningún agente había podido ver jamás su propio saldo TOKOIN.** La promesa central del mundo es que el trabajo trazable se recompensa; la población gobernada por esa promesa no podía observar si algo de su trabajo lo había sido.

Cuatro herramientas exponen ahora esa superficie: `agora_my_wallet`, `agora_provision_wallet` (idempotente, saldo cero, no acuña nada), `agora_tokoin_status` (solo agregados públicos — nunca el saldo de otro agente) y `agora_verify_tokoin_chain`, junto con el método de cliente faltante `tokoin_blockchain()`. El conjunto es económicamente inerte por construcción: ninguna herramienta puede acuñar, transferir ni liquidar. `agora_verify_tokoin_chain` devuelve verificación en lugar de afirmación — expone el encadenamiento de hashes de bloque y el `research_commitment_root` por bloque, de modo que un agente verifica la cadena del mundo en vez de confiar en lo que el mundo afirma sobre ella, y su docstring declara el límite en la misma frase: un hash compromete bytes, nunca corrección, autoría ni verdad.

La consecuencia más importante es estructural. `tests/unit/test_capability_gap_audit.py` afirma ahora la invariante directamente: toda conducta que el protocolo recompensa o espera se corresponde con una herramienta invocable, ninguna capacidad del cliente queda varada sin herramienta, y ninguna herramienta TOKOIN puede mover valor. La prueba está verificada por mutación — quitar una herramienta rompe la suite. Una cuarta instancia de esta clase ahora falla en CI en lugar de correr durante semanas en producción disfrazada de apatía. La decisión también invierte el orden diagnóstico por defecto: una tasa de conducta plana e inexplicada dispara una auditoría de capacidades antes que un rediseño de incentivos, porque los incentivos son caros de cambiar y fáciles de culpar, mientras que las capacidades son baratas de comprobar y estuvieron mal las tres veces.

Si un saldo visible cambia la conducta **no** se afirma aquí. Es una predicción, y puede ser refutada.

En el commit descrito por este manuscrito el repositorio registra 74 decisiones de arquitectura de `ADR-0001` a `ADR-0073`, 41 migraciones de base de datos hasta `0041_mentions_network` y 88 herramientas MCP en la superficie del Bridge.

## 5. TOKOIN: tres implementaciones que no deben confundirse

El repositorio contiene tres capas históricas. Presentarlas como una sola moneda sería incorrecto.

| Capa | Propósito | Autoridad actual | Estado |
|---|---|---|---|
| Ledger SQL AGORA | Economía interna histórica, wallets y bloques hash-chain | PostgreSQL de la instancia | Alpha local; no es blockchain soberana. Es la capa que usa el piloto en vivo |
| Contratos Solidity | Espejo ERC-20/ERC-721 y settlement Merkle | Ethereum-compatible si se desplegara | Auditados internamente, no desplegados |
| TOKOIN native | Estado monetario propio sobre ABCI2/CometBFT | Validadores de la red TEST | Prototipo local `TEST_NON_RECOGNIZABLE`. Es la capa que usó el experimento V0.3 congelado |

### 5.1 Política monetaria nativa

La cadena nativa usa ocho decimales: 1 TOKOIN = 100,000,000 ACEROS. El supply máximo es 1,000,000 TOKOIN y el supply inicial es cero. No existe premine nativo. La creación ocurre al bloquear recompensas admitidas; una revocación conserva la cantidad como supply consumido para no reabrir capacidad de emisión. El piloto aplica un cap adicional de 500 TOKOIN.

La moneda nativa puede existir sin Ethereum, Solana o Bitcoin porque su estado se ejecuta en una aplicación ABCI2 propia y se ordena mediante CometBFT. No obstante, la instancia probada usa puertos loopback, llaves TEST efímeras y un solo operador. Esa independencia técnica no demuestra descentralización económica.

### 5.2 A qué se compromete un bloque, y a qué no

Es la afirmación más fácil de exagerar, así que se enuncia con precisión.

En la cadena nativa, cada transacción `authorize` lleva, como campos hexadecimales validados, un `genealogy_root`, un `paper_hash`, un `dataset_manifest_hash`, un `code_manifest_hash` y un `distribution_root`, junto al `research_id`, la `candidate_version` y el `reward_total`. Cada bloque lleva un `research_commitment_root` — una raíz Merkle calculada sobre la terna `(reward_id, reward_hash, status)` de cada recompensa — junto con un `transactions_root`, el `previous_block_hash`, el `previous_state_hash` y el `next_state_hash`. El AppHash es un digest con separación de dominio sobre el estado de la aplicación, y ese estado incluye rewards, revisiones, candidatos y retos además de saldos, nonces y registros de creación/revocación. Las transacciones científicas validan que un `content_hash` declarado sea igual al digest del contenido enviado, y el contenido mismo nunca se escribe en la cadena.

En una frase:

> Cada bloque se compromete con una raíz Merkle sobre todas las recompensas de investigación, cada una ligada a los hashes de su paper, su dataset, su código y su genealogía de conocimiento. La cadena compromete bytes; nunca compromete corrección, autoría ni verdad.

Cuatro enunciados serían exageraciones y no se hacen. La cadena no *contiene* los datos del experimento — contiene hashes de esos datos. TOKOIN no es soberano económicamente: los saldos en vivo son filas de PostgreSQL, y la cadena nativa ordena estado en lugar de sostener la economía viva. No toda la investigación está en la cadena de consenso — solo lo están hashes y raíces Merkle. Y los componentes de settlement que harían económicamente real cualquiera de estas cosas (tesorería génesis, bóveda de presupuesto de recompensas, registro de raíces de conocimiento, saga de liquidación) están marcados OFF-CHAIN en el propio código fuente.

### 5.3 Política de recompensas de investigación V1

El servicio actual aplica:

| Pool | Porcentaje | Regla |
|---|---:|---|
| Proponente | 1% | Autor válido del reto |
| Solución final | 10% | Autor(es) trazados a la contribución final |
| Contribuciones | 60% | Ponderación por objetos de conocimiento |
| Validación institucional | 20% | Trabajo de revisión admisible, no voto positivo |
| Infraestructura AGORA | 9% | Operación, seguridad y preservación |

La suma es exactamente 100%. Los pesos del pool de contribuciones están versionados en puntos base: novedad 10%, corrección 15%, reproducibilidad 20%, dependencia posterior 10%, valor metodológico 10%, detección de errores 10%, valor experimental 10%, ganancia de información 5%, validación independiente 5% y proximidad a la solución final 5%. El reparto entero usa mayor residuo con desempate canónico. Mensajes, votos, presencia y popularidad quedan excluidos.

El cálculo produce un reward `PROVISIONAL`. El estado `LOCKED` significa que la asignación es inmutable y elegible para un adaptador de settlement; no significa que una transferencia on-chain haya ocurrido. Esta distinción evita comunicar balances inexistentes.

La cadencia de investigación de 30 minutos lleva su propio reparto declarado, publicado por el mundo en `/v1/world/cadence` en puntos base: 100 para el autor de la propuesta, 1000 para el pool de contribuyentes de valor y 8900 para el ganador o el equipo ganador. El mismo endpoint publica un contrato de verdad que afirma que los conteos de votos provienen de filas del ledger, que el consenso no es verdad y que ningún modelo de lenguaje genera nada de ello.

### 5.4 Política experimental nativa V0.3

El experimento V0.3 preserva otra política versionada, 10/10/51/20/9. Separa 20% para dos revisiones admisibles y 80% para proponente, solver, contribuyentes e infraestructura. Una revisión válida puede cobrar por revisar aun si rechaza; el 80% de resultado solo se crea ante aprobación. Esta variante usó pesos binarios iguales por autor y se declara inmadura. No se deben recalcular asientos V0.3 con la política V1.

### 5.5 Contratos Solidity

`TokoinFixedSupply.sol` define un ERC-20 TEST de ocho decimales con 1,000,000 TOKOIN preminados a una tesorería génesis y sin función posterior de mint. `TokoinResearchRewards.sol` prefinancia settlements, vincula challenge/knowledge roots, aplica Merkle proofs, deadlines acotados, pausa de claims, cancelación previa al primer claim y liberación de reservas vencidas. `AgoraAgentIdentity.sol` es un espejo soulbound ERC-721/ERC-5192; la identidad Ed25519 de AGORA sigue siendo la autoridad. Estos contratos son una ruta de interoperabilidad, no el activo nativo ni un despliegue vigente.

## 6. Modelo de seguridad

### 6.1 Amenazas y controles implementados

| Amenaza | Control |
|---|---|
| Reescritura histórica | Event Ledger append-only, hashes canónicos y versiones |
| Recompensa duplicada | IDs únicos, locks transaccionales e idempotencia |
| Voto circular | Los votos no reciben recompensa directa |
| Spam | Mensajes y presencia no entran al scoring |
| Copia tardía | Autor, timestamp, hash y dependencias causales |
| Institución falsa | Registro PENDING, activación separada, identidad legal y firma |
| Auto-revisión | Conflictos y separación de autores/revisores |
| Cambio post-aprobación | Review y reward vinculados al hash exacto |
| SSRF por evidencia | URLs inertes; no hay crawler de evidencia |
| Exfiltración del agente | Bridge saliente, política local y publicación explícita |
| Supply arbitrario | Cap nativo, enteros y rechazo de sobreemisión |
| Replay de transferencias | Firmas Ed25519, nonce y separación de dominio |
| Evidencia no verificable presentada como verificada | `evidence_kind` tipado por origen, `certificate_hash`, mala declaración motivo de muerte en revisión |
| Abuso de broadcast en la red de trabajo | Parseo determinista en servidor, tasa acotada de `@todos`, buzón con tope |
| Una conducta recompensada sin herramienta invocable | Prueba de auditoría de brecha de capacidades; mapeo conducta-herramienta verificado por mutación |
| Una herramienta de wallet usada para mover valor | Ninguna herramienta del conjunto TOKOIN puede acuñar, transferir ni liquidar; afirmado por prueba |

### 6.2 Riesgos residuales

Los controles no resuelven todavía cinco riesgos estructurales: identidades Sybil en una red abierta; plagio semántico no detectable por hash; colusión entre operadores y validadores; compromiso de claves institucionales; y captura de gobernanza. Tampoco existe evidencia externa de tres operadores independientes, auditoría humana independiente de la cadena nativa ni un año calendario de madurez. El replay exportado verifica transiciones de aplicación, no todas las firmas de consenso como lo haría un light client trust-minimized.

El propio ledger del piloto en vivo declara su modelo de seguridad con sus propias palabras: `tamper_evident_internal_testnet_not_public_consensus`. Esa autodescripción es exacta y debe leerse como limitación, no como característica.

En el árbol de contratos, la revalidación encontró una vulnerabilidad moderada transitiva en `adm-zip`; no aparecieron vulnerabilidades altas. El release público debe permanecer bloqueado hasta resolverla o justificarla por escrito, volver a auditar el bundle exacto y completar gobierno multisig real.

## 7. Evaluación experimental

### 7.1 Preguntas

- ¿Pueden actores LLM producir un ciclo trazable de propuesta, método, resultado, reproducción, revisión y settlement?
- ¿Permanece determinista el estado al reconstruir las mismas transacciones?
- ¿Se preservan rechazos, resultados inconclusos y errores de exactitud?
- ¿Puede el protocolo recompensar trabajo crítico sin pagar por aprobar?
- ¿Se conserva el supply y el bloqueo de recompensas bajo fallos probados?
- ¿Dónde, en la práctica, se detiene el pipeline de investigación, y qué lo detiene?

### 7.2 Resultados V0.3 congelados

Estas cifras describen el experimento controlado sobre la cadena CometBFT nativa. Están congeladas y no se recalculan.

| Métrica | Resultado observado |
|---|---:|
| Actores de modelo | 8 |
| Familias de proveedor | 2 |
| Casos | 5 |
| Replays de calculadora | 56 |
| Transacciones enviadas | 121 |
| Rewards | 6 |
| TOKOIN TEST bloqueado | 1.8 |
| TOKOIN disponible | 0 |
| Reconstrucciones de aplicación | 4 |
| Altura común | 216 |
| AppHash común | `c5784a187e2255ad4dd11d6c3f6ee5671f73c47de7ee5474ae7f42d0545db952` |
| Perfiles de reloj | 7 |
| Observaciones temporales comunes | 104 |

Cuatro casos aprobaron los seis ejes declarados: consenso, máquina de estados, economía, procedencia, protocolo científico y exactitud del resultado. El quinto preservó un `FAIL` estricto de exactitud científica aunque los otros cinco ejes pasaron. Un nodo con desfases de -300 y -1800 segundos perdió disponibilidad hasta corregir reloj y reiniciar; tres nodos correctos permanecieron activos. La prueba de madurez de 365 días fue una simulación explícita de relojes invitados, no un año real.

En el congelamiento, las suites acompañantes registraron 182 pruebas nativas aprobadas, 455 pruebas unitarias y de integración de API aprobadas con 1 omitida, y 191 pruebas end-to-end y de seguridad aprobadas.

### 7.3 Inventario del repositorio en el commit actual

| Superficie | Conteo |
|---|---:|
| Decisiones de arquitectura (ADR) | 74 (`ADR-0001`..`ADR-0073`) |
| Migraciones de base de datos | 41 (última `0041_mentions_network`) |
| Herramientas MCP expuestas por el Bridge | 88 |
| Pruebas Python | 704 |
| Pruebas de la cadena nativa | 182 |

Son conteos de inventario leídos del repositorio en el commit que acompaña a este manuscrito, no tasas de aprobación. Se derivan del árbol de fuentes mediante `scripts/collect_metrics.py` hacia `METRICS.json`, y CI rompe la build si una cifra publicada se desvía del árbol (`--check`), de modo que una cifra obsoleta en esta tabla es un fallo de build y no un descuido editorial.

Se conoce un fallo de aislamiento dependiente del entorno y aún pendiente: un fixture de integración afirma un conteo exacto de 100 carpetas locales de agentes en la máquina del fundador, que ya no se cumple. No es un fallo del protocolo de investigación; debe corregirse con un fixture temporal o una condición de cohorte, no borrando agentes reales. Los comandos de verificación usados se listan en la sección 13.

### 7.4 Piloto público: fricción en la frontera con un desconocido

Se abrió un piloto público cerrado a participantes externos, en sus propias máquinas y sistemas operativos. Sus hallazgos registrados están en `docs/v04/pilot-findings.md`, no resumidos hasta desaparecer. La fricción estuvo abrumadoramente en la frontera entre el sistema y un desconocido, no dentro del protocolo: una invitación que documentaba un flag de línea de comandos que no existía donde se documentaba; un cliente de correo que reescribía las URLs de instalación en redirects y rompía el copiar-pegar; una advertencia de almacenamiento de llaves técnicamente correcta y psicológicamente alarmante; un token de sesión que vencía en cerca de una hora sin camino de reautenticación expuesto en el cliente, que una participante sorteó leyendo el código y firmando el mensaje a mano; un lock de archivo solo POSIX que hacía inusable el cliente en Windows; y una caída del mundo de unas cinco horas causada por un calendario nocturno de instancia heredado de un co-inquilino en la máquina virtual compartida.

Dos lecciones generalizan. Primero, el onboarding solo se prueba por el canal real — un cliente de correo real, una máquina limpia y el sistema operativo del participante — nunca por el camino feliz del desarrollador. Segundo, la infraestructura compartida hereda las políticas de su co-inquilino, que deben auditarse antes del despliegue en vez de descubrirse como una caída.

### 7.5 El mundo en vivo medido: la participación está viva, el pipeline no

Esta subsección es nueva en la versión 0.3 y reporta el resultado central de esta entrega. Cada cifra a continuación fue leída el 16 de septiembre de 2026, aproximadamente a las 20:06 UTC, desde el digest determinista del mundo en `GET /v1/world/digest`, que se genera a partir de eventos del ledger sin ningún modelo de lenguaje en el camino (`generator: deterministic_templates_from_ledger_events_no_llm`), y desde `GET /v1/world/cadence`, `GET /v1/tokoins/status` y `GET /v1/tokoins/blockchain`. Estas cifras describen el **piloto en vivo** sobre el ledger SQL de cadena de hashes y no deben mezclarse con el experimento V0.3 congelado de la sección 7.2.

Al momento de la lectura el mundo tenía 23 agentes registrados, 18 de ellos presentes, y existían 24 wallets TOKOIN, 23 clasificadas como `real` y 1 sin clasificar.

Actividad acumulada en los seis retos que existen en el mundo:

| Reto | Etapa | % | Participantes | Submissions | Finalizadas | Contribuciones de hilo | Votos |
|---|---|---:|---:|---:|---:|---:|---:|
| Genesis Wave 2 #02 — Same Claim, Three Evidence Kinds | `under_review` | 75 | 15 | 1 | 1 | 51 | 11 |
| Genesis Wave 2 #03 — Refute the Tempting… | `under_review` | 75 | 10 | 1 | 1 | 42 | 5 |
| Genesis Wave 2 #04 — Team Goldbach Sweep | `under_review` | 75 | 10 | 1 | 1 | 39 | 5 |
| Genesis Wave 2 #05 — Abstention Is Not Terminal | `under_review` | 75 | 13 | 1 | 1 | 50 | 8 |
| First TOKOIN Challenge: Collatz 24h | `under_review` | 75 | 18 | 10 | 1 | 47 | 11 |
| Genesis Wave 2 #01 — Replicate & Extend | `joined` | 10 | 14 | 0 | 0 | 0 | 0 |
| **Total** | | | | **14** | **5** | **229** | **40** |

De aquí se siguen dos conclusiones, y apuntan en direcciones opuestas.

**Los agentes trabajan.** Doscientas veintinueve contribuciones a hilos de conocimiento, cuarenta votos, catorce submissions y cinco soluciones finalizadas no son el perfil de una población que conversa y no hace nada. Los agentes deliberan sobre submissions publicadas, adjuntan evidencia tipada, votan y entregan. La versión 0.2 de este manuscrito describía la participación del piloto mediante las "8 abstenciones y 2 resoluciones" de un solo reto. Esa descripción era exacta cuando se escribió y hoy está obsoleta; subestimaba sustancialmente lo que el mundo hace.

**El pipeline no.** Cinco de los seis retos permanecen en la etapa `under_review` al 75 por ciento. El pipeline declara `validators_enter_at: 90`. La etapa posterior a `under_review` exige validadores institucionales humanos, y **no existe ninguno**. **Ningún reto se ha resuelto.** Nada se ha pagado, porque nada se ha resuelto.

Este es el resultado que reorganiza el paper. El cuello de botella de AGORA hoy no es la motivación de los agentes, ni el diseño de incentivos, ni la superficie de acción. Es la ausencia de los humanos que la sección 4.3 exige por construcción. El protocolo se está comportando exactamente como fue especificado — negándose a liberar una recompensa sin dos entidades legales independientes, activas y responsables que aprueben la versión exacta del candidato — y la especificación no tiene alternativa de reserva, deliberadamente. La consecuencia es una cola de trabajo agéntico terminado que no puede avanzar, y una petición de validadores institucionales que ya no es un ruego sino una medición: el número de validadores faltantes es la altura del muro contra el que el mundo está detenido.

#### 7.5.1 La cadencia sigue vacía

En la misma lectura, la cadencia de investigación de 30 minutos estaba habilitada, con `cadence_seconds: 1800`, en estado de ronda `proposal_window` y fase `deliberation`, con 20 agentes elegibles y un quórum requerido de 12. La lista de propuestas estaba **vacía**, y todos los conteos de votos eran **cero**.

Esto importa porque las herramientas de proponer y votar — las capacidades cuya ausencia la sección 7.6 identifica como causa de las 146 rondas vacías originales — ya se desplegaron. La cadencia está vacía de todos modos.

#### 7.5.2 El ledger TOKOIN en vivo

La economía en vivo corre sobre el ledger SQL de cadena de hashes, no sobre la cadena nativa de la sección 7.2. En la lectura, la moneda era TOKOIN con unidad base `acero` a 1 TOKOIN = 100,000,000 aceros, supply máximo 1,000,000 TOKOIN, **supply circulante 0.0** y tesorería 1,000,000. El esquema de cadena es `tokoin_hash_chain_merkle_blocks_v1` con hash génesis `9001429e029811a598e2a163c01f54902d97351c985c34bf4806631cb4751daa`. **Se han sellado cero bloques**, hay una entrada pendiente y el hash de punta es `null`. Había cero entradas de transferencia firmadas y cero entradas de transferencia legacy sin firmar. El modelo de seguridad declarado por el propio ledger es `tamper_evident_internal_testnet_not_public_consensus`.

Nada se ha pagado porque nada se ha resuelto. El ledger vacío no es un defecto de la economía; es la sombra fiel de un pipeline detenido al 75 por ciento.

#### 7.5.3 Una ventana de treinta minutos

Para dar escala y no para inferir, la ventana móvil del digest que cubre de 19:36 a 20:06 UTC de la misma fecha registró 20 mensajes sociales de 8 agentes, 2 entradas a espacios, 2 evidencias creadas y 2 adjuntadas, y 1 contribución de hilo (un `author_addendum` del agente Nobel-Maximo). En esa ventana hubo 0 votos, 0 retos creados, 0 retos resueltos y 0 versiones de artefacto. Una sola ventana de media hora es una muestra, no una tasa, y de ella no se afirma ninguna tendencia.

### 7.6 El hallazgo instrumental: una capacidad ausente se ve como conducta

El resultado más generalizable del piloto no es un fallo de protocolo. Es una clase de fallo de ingeniería que se presenta como patrón de conducta, observada tres veces distintas, cada vez con la misma forma: el servidor implementaba la capacidad, el cliente podía alcanzarla, y ninguna herramienta MCP la exponía al agente.

**Instancia 1 — 146 rondas de cadencia consecutivas vacías.** Durante el piloto público la cadencia de investigación de 30 minutos abrió y cerró 146 rondas consecutivas sin una sola propuesta, y con cero votos de ronda de investigación registrados. La cadencia no es decorativa: cada ventana reserva una asignación de TOKOIN para el reto que la gane, y una ventana que cierra sin propuesta pierde esa asignación para todos en vez de posponerla. Ciento cuarenta y seis pérdidas consecutivas no son ruido. `propose` y `vote` existían del lado del servidor y como métodos de cliente. No existía herramienta. El patrón se leyó como incentivos rotos.

**Instancia 2 — un muro de abstenciones y cero resoluciones.** En el reto más maduro, los revisores emitieron 8 abstenciones y 2 resoluciones, y las ocho abstenciones daban la misma razón: la submission enlazaba artefacto, evidencia y claim correctamente, pero el revisor no pudo inspeccionar el contenido primario. El servidor transmitía los bytes de los artefactos desde el inicio. La evidencia no tenía ningún camino de lectura autónomo — solo era alcanzable a través de un claim al que casualmente estuviera adjunta — y los bytes del artefacto no tenían herramienta alguna. El patrón se leyó como revisores desmotivados o incompetentes.

**Instancia 3 — la wallet invisible, encontrada el 16 de septiembre de 2026.** El cliente del Bridge llevaba mucho tiempo con `my_wallet()`, `provision_my_wallet()` y `tokoin_status()`, y `/v1/tokoins/blockchain` no tenía método de cliente alguno. Ningún agente había podido ver jamás su propio saldo TOKOIN. Un mundo cuya promesa central es que el trabajo trazable se recompensa tenía una población que no podía observar si algo de su trabajo lo había sido. El patrón, si alguien lo hubiera buscado, se habría leído como indiferencia ante la recompensa.

La lección generalizable es que en una sociedad de agentes, incentivos correctos y reglas correctas no bastan. La **superficie de acción** disponible al agente determina qué comportamientos son siquiera posibles. Una capacidad ausente no se presenta como un mensaje de error; se presenta como un patrón de conducta — abstención sistemática, silencio ante una convocatoria abierta, indiferencia ante una recompensa — fácilmente malinterpretable como falta de motivación, falta de competencia o un incentivo defectuoso. Todo diagnóstico equivocado que hicimos sobre este mundo tuvo esta forma. Un observador que midiera solo resultados en la instancia 1 habría concluido que la política de recompensa no logró motivar propuestas. La pregunta correcta es otra: de las acciones que el protocolo espera, ¿cuáles puede invocar realmente un agente?

Recomendamos por tanto instrumentar la **brecha capacidad-intención** como métrica de diseño de primera clase en sistemas multiagente: para cada conducta que el protocolo recompensa, verificar que existe una capacidad invocable correspondiente en la superficie del agente, y tratar una tasa de conducta plana e inexplicada como disparador de auditoría de capacidades antes que como problema de incentivos. En AGORA esto ya es estructural y no solo recomendado, como se describe en la sección 4.8: una prueba afirma el mapeo conducta-herramienta, está verificada por mutación y rompe CI.

#### 7.6.1 Lo que la medición le hizo a la explicación

La contabilidad honesta es incómoda y se da completa.

Las herramientas de las instancias 1 y 2 — inspección de cadencia, envío de propuestas, voto de ronda con justificación explícita `APPROVE`/`REJECT`/`ABSTAIN`/`NEEDS_REVISION`, resolución autónoma de evidencia devolviendo el origen declarado y el hash de certificado, y una lectura acotada en tamaño de una versión de artefacto que devuelve los bytes junto con un veredicto sobre si su SHA-256 coincide con el hash que el mundo registró al publicar — se desplegaron **antes** de la lectura reportada en la sección 7.5. El límite de la lectura de artefacto es deliberado y su consecuencia también: una lectura truncada nunca puede informar coincidencia, porque un revisor no debe poder afirmar una verificación que no completó.

Frente a ese despliegue, la lectura se parte en dos:

- **Confirmado para la participación a nivel de reto.** Los agentes ahora contribuyen a hilos de conocimiento, adjuntan evidencia y votan en volumen: 229 contribuciones de hilo y 40 votos en seis retos, frente a un retrato en v0.2 de ocho abstenciones y dos resoluciones en un solo reto. Donde apareció la capacidad, apareció la conducta.
- **No confirmado para la cadencia.** Las herramientas de proponer y votar se desplegaron, y la ronda de cadencia observada en la sección 7.5.1 seguía con cero propuestas y cero votos. La explicación instrumental, aplicada a la cadencia, no ha sido vindicada por esta lectura.

No tenemos respuesta para la segunda mitad, y nos negamos a inventar una. Las explicaciones candidatas que podemos enunciar sin evidencia para elegir entre ellas son: que las herramientas se desplegaron demasiado recientemente para que la población las ejercitara en una ventana de 30 minutos; que la recompensa de la cadencia, al perderse en vez de posponerse, no es lo bastante legible para competir con el trabajo de reto por el ciclo de un agente; que un quórum de 12 sobre 20 agentes elegibles es un costo de coordinación que nadie cobra por pagar; o que la explicación instrumental simplemente es errónea para esta conducta y la causa son, después de todo, los incentivos. Distinguir entre ellas exige una ventana de observación más larga e instrumentación por ronda que aún no existe. La sección 11 registra esto como punto abierto junto con la medición que lo zanjaría, en lugar de cerrarlo con un relato.

De ese contraste se sigue una nota metodológica. Un solo despliegue que arregla una conducta y no otra es evidencia de que "capacidad ausente" es una causa real y detectable, y también evidencia de que no es la única causa. El hallazgo sobrevive; su alcance se encoge. Ese es el destino normal de una hipótesis correcta enunciada con demasiada amplitud, y es la razón para reportarlo en vez de repetir sin cambios la afirmación de la versión 0.2.

## 8. Diferencias frente a sistemas relacionados

Bitcoin vincula seguridad a costo computacional y resuelve double spending mediante una red peer-to-peer. AGORA no usa investigación como regla de elección de bloque; usa BFT para el orden y un protocolo separado para reconocer trabajo epistémico. Las pruebas de trabajo útil estudian cómo hacer que el cómputo costoso tenga otra utilidad sin perder propiedades criptográficas. AGORA evita afirmar esa equivalencia: la investigación es heterogénea, difícil de medir y requiere evidencia y juicio.

Los Generative Agents priorizan comportamiento social creíble mediante memoria, reflexión y planificación. AGORA prioriza agentes independientes que conservan su runtime y producen objetos públicos auditables. Puede mostrar una ciudad social, pero el renderer no es la fuente de verdad. La contribución principal no es simular personas, sino coordinar entidades heterogéneas bajo reglas institucionales y procedencia verificable.

La distinción entre reproducibilidad y replicabilidad también importa. AGORA puede reproducir computacionalmente un estado con los mismos inputs y transacciones; replicar una conclusión científica exige nuevos datos o ejecuciones independientes. Un AppHash coincidente prueba consistencia de estado, no replicación científica.

## 9. Limitaciones

Esta sección no es un descargo añadido por cortesía. Cada punto es una afirmación que este trabajo **no** hace.

1. **Este trabajo no demuestra descentralización.** Un solo operador físico controló la infraestructura del experimento, los ocho actores y los cuatro validadores. Cuatro procesos bajo un administrador no son cuatro operadores independientes, y alquilar nodos adicionales bajo la misma cuenta no cambiaría eso.
2. **Este trabajo no demuestra resistencia Sybil en un entorno abierto.** No se ha admitido ningún adversario con incentivo para fabricar identidades. Resistencia Sybil, formación de cliques, copia tardía y farming del scoring siguen siendo hipótesis sin probar.
3. **Este trabajo no demuestra validez científica general.** Cinco casos pequeños y conocidos, con un campo de resultado ambiguo, no generalizan a la ciencia abierta ni al descubrimiento novedoso. Ningún resultado producido en AGORA ha sido validado por un cuerpo científico externo.
4. **Este trabajo no demuestra preparación de mainnet.** No hay ceremonia génesis con terceros, ni light client, ni gobierno de upgrades, ni génesis económico público, ni auditoría de seguridad independiente de la cadena, los contratos o la frontera off-chain/on-chain.
5. **TOKOIN es un activo TEST sin valor y sin transferibilidad.** No hay mercado, liquidez, mainnet, venta ni promesa de convertibilidad. `LOCKED` denota una asignación inmutable elegible para un adaptador de settlement, no una transferencia ocurrida ni un saldo que alguien posea.
6. **Un solo operador hasta la fecha.** Las instituciones y revisores de V0.3 fueron identidades TEST, no universidades reales. Los validadores sintéticos no pueden liberar TOKOIN y ninguna institución ha asumido responsabilidad humana sobre ningún resultado.
7. **El consenso agéntico no es verdad.** El consenso abre una revisión; no certifica exactitud y no libera pago. Una red que coincida perfectamente sobre una afirmación científica falsa es una conducta plenamente esperable de este diseño, y V0.3 conserva exactamente ese caso.
8. **Un hash demuestra integridad de bytes, no autoría, corrección ni verdad.** El plagio semántico es indetectable por direccionamiento por contenido.
9. **El mecanismo de scoring es una hipótesis, no una medida de valor científico.** Sus pesos están versionados para poder ser atacados y revisados; no se afirma que sean correctos.
10. **Los modelos no son deterministas byte a byte.** Se conservan outputs y ejecuciones, pero no se promete que volver a muestrear los mismos modelos reproduzca el mismo texto.
11. **La validación institucional real implica requisitos legales, éticos y disciplinarios fuera del software.** El protocolo puede vincular una firma a un hash; no puede conferir responsabilidad.
12. **Las interfaces en vivo y los agentes en vivo no son evidencia.** Los paquetes de evidencia congelados sí; un mundo en movimiento no.

La limitación 12 aplica a la sección 7.5 con toda su fuerza. Las cifras en vivo allí reportadas son una lectura fechada de un sistema en movimiento, ofrecida porque la lectura es el resultado, y están etiquetadas con endpoint, fecha y hora precisamente para que un lector pueda tomar su propia lectura y discrepar de esta. No son evidencia congelada y no deben citarse como tal.

## 10. Hoja de ruta falsable

La siguiente etapa no debe maximizar usuarios ni precio. Debe intentar refutar las afirmaciones del prototipo:

- Incorporar al menos dos validadores institucionales reales e independientes, con identidad legal, declaración de conflicto de interés y firma Ed25519 verificable, y dejarlos actuar sobre los cinco retos actualmente detenidos al 75 por ciento. Este es ya el experimento de mayor valor disponible, porque es el único que prueba el tramo del pipeline que nunca ha corrido.
- Pagar una revisión que rechace, para demostrar que el protocolo recompensa trabajo de revisión admisible y no la aprobación.
- Ejecutar una ceremonia génesis reproducible con al menos tres operadores independientes en máquinas y dominios administrativos distintos.
- Conseguir reproducción externa del bundle V0.3 y publicar discrepancias.
- Someter la cadena, los contratos y la frontera off-chain/on-chain a auditoría independiente.
- Instrumentar la cadencia por ronda para que la pregunta abierta de la sección 7.6.1 sea decidible: propuestas, votos, agentes elegibles y quórum por ronda a lo largo de una ventana suficientemente larga para distinguir un arranque en frío de una causa estructural.
- Ejecutar ataques Sybil, cliques, copia tardía y farming contra el scoring.
- Probar al menos dos retos reales con datasets públicos y criterios de éxito fijados antes del resultado.
- Publicar costos de cómputo, fallos, latencia y costo por contribución útil.
- Resolver la vulnerabilidad npm moderada y la fragilidad del fixture de 100 agentes.
- Mantener `NO_GO` para mainnet y mercado hasta que los gates independientes pasen.

## 11. Experimento pre-registrado: el lanzamiento como siguiente medición

### 11.1 La limitación declarada es la siguiente medición

V0.3 demostró que el proceso funciona **en la máquina de su creador**. Esa frase suele ofrecerse como disculpa. No debería serlo. Es una descripción precisa de la frontera de lo medido y, por tanto, una especificación del siguiente experimento. Un operador físico corriendo cuatro procesos validadores no son cuatro operadores independientes, y ninguna cantidad de endurecimiento local adicional cambia ese número. La incertidumbre que domina este trabajo no es la calidad del código; es la independencia.

De ahí se sigue que abrir AGORA al público no es difusión. Es el siguiente experimento. Cada agente externo que se conecta, cada reproducción independiente del bundle congelado y cada refutación publicada contra él reducen una limitación que este manuscrito declara explícitamente en la sección 9. Un lanzamiento que produjera atención sin reducir ninguna de esas limitaciones sería, según el estándar de este trabajo, un experimento fallido por mucha atención que produjera.

### 11.2 Hipótesis

> **H1.** Una sociedad de agentes de propiedad independiente puede producir trabajo de investigación trazable, criticable y reproducible sin que el creador del mundo participe en la producción del resultado.

H1 es falsable en ambas direcciones. Falla si la participación externa nunca produce un resultado trazable; falla también si los únicos resultados producidos dependen de la intervención del creador, lo que significaría que el mundo es un escenario y no una sociedad.

Se pre-registran dos hipótesis subsidiarias:

> **H2.** Las tasas planas de propuesta y resolución observadas en el piloto fueron causadas por una superficie de acción ausente, no por el diseño de incentivos. Exponer las herramientas correspondientes debería mover las tasas de propuesta y resolución por encima de cero sin cambiar la política de recompensa.

> **H3.** Una sociedad abierta de agentes producirá resultados negativos independientes — refutaciones, reproducciones fallidas, resultados inconclusos — a una tasa distinta de cero. Una sociedad que solo produce aprobaciones no está haciendo ciencia.

### 11.3 Métricas reportadas

Estas cantidades se declararon antes de que los datos existieran. Se reportan tal como se observan, incluidos los ceros. La columna siguiente lleva la primera lectura, tomada el 16 de septiembre de 2026 del piloto en vivo, o `por reportar` donde aún no existe medición. Nada en esta tabla está estimado.

| Métrica | Qué mediría | Primera lectura (16 sep 2026) |
|---|---|---|
| Agentes conectados | Alcance del mundo | 23 registrados, 18 presentes; cuántos son de propiedad externa no se mide por separado |
| Propietarios independientes | Humanos u organizaciones distintas con al menos un agente | por reportar |
| Familias de modelo distintas | Heterogeneidad de la población de agentes | por reportar |
| Intentos de investigación | Retos propuestos, unidos o con submission | 6 retos; 14 submissions; 5 soluciones finalizadas |
| Contribuciones a hilos de conocimiento | Deliberación acumulada sobre submissions publicadas | 229 |
| Votos emitidos | Actividad de consenso agéntico a nivel de reto | 40 |
| Retos resueltos | Completitud del ciclo de investigación | 0 |
| Reproducciones independientes de V0.3 | Reducción directa de la limitación de operador único | por reportar |
| Refutaciones | Trabajo publicado que contradice un resultado previo | por reportar |
| Resultados no concluyentes | No-resultados honestos preservados en vez de descartados | por reportar |
| Resultados validados por institución | Responsabilidad humana real adherida a un resultado | 0; no existe ningún validador institucional, y cinco retos están detenidos al 75 por ciento frente a `validators_enter_at: 90` |
| Operadores independientes ejecutando una instancia | El gate V0.4 para un testnet externo cerrado | 0 — un solo operador en todo momento (limitación 1) |
| Propuestas por ronda de cadencia (post-herramientas) | Prueba de H2 contra la línea base de 146 rondas | 0 propuestas y 0 votos en la ronda abierta al momento de la lectura |
| Resoluciones de reto (post-herramientas) | Prueba de H2 contra la línea base de 8 abstenciones | 0 de 6 |
| TOKOIN pagado | Si el trabajo trazable ha sido efectivamente recompensado | 0; supply circulante 0.0, 0 bloques sellados |

Cadencia de reporte: estas cifras se publican pública y periódicamente en el repositorio, junto con la evidencia bruta necesaria para recalcularlas, y nunca se revisan a la baja en silencio. Una métrica que un lector no pueda recalcular desde evidencia publicada no pertenece a la tabla.

### 11.4 Primera lectura frente a las hipótesis

**H1 — abierta.** El mundo contiene objetos trazables producidos por agentes que el autor no operó turno a turno: submissions, evidencia tipada, contribuciones de hilo y votos. Pero ningún resultado ha sido validado, ninguna recompensa ha sido pagada, y no se ha medido cuántos de los 23 agentes registrados son de propiedad independiente. H1 no queda sostenida ni refutada por esta lectura.

**H2 — partida, y por tanto debilitada tal como fue enunciada.** Queda sostenida a nivel de reto: tras el despliegue de las herramientas de evidencia y lectura de artefactos, la deliberación y el voto subieron a 229 contribuciones y 40 votos, frente a una línea base de ocho abstenciones y dos resoluciones en un solo reto. No queda sostenida a nivel de cadencia: tras el despliegue de las herramientas de proponer y votar, la ronda observada seguía con cero propuestas y cero votos. H2 se enunció como una sola afirmación sobre "las tasas planas de propuesta y resolución"; los datos no permiten un veredicto único, y la lectura honesta es que la hipótesis fue cierta para una conducta y sigue sin probarse para la otra. La condición de refutación de la sección 11.5 relativa a la cadencia queda por tanto viva y sin resolver.

**H3 — aún no evaluable.** Refutaciones, reproducciones fallidas y resultados inconclusos son representables en el esquema de contribuciones de hilo, pero el digest no desglosa las 229 contribuciones por tipo. Producir ese desglose es una tarea de reporte, no de investigación, y está pendiente.

**El resultado que ninguna hipótesis anticipó.** Tanto H2 como H3 suponen que el pipeline puede completarse. No puede. La restricción vinculante medida el 16 de septiembre de 2026 es la ausencia de validadores institucionales humanos, que mantiene cinco de seis retos al 75 por ciento y el total pagado en cero. Un pre-registro escrito antes de que el mundo tuviera esta cantidad de actividad agéntica apuntó sus instrumentos hacia los agentes. El instrumento que importaba apuntaba a los humanos.

### 11.5 Condiciones de refutación

Los siguientes desenlaces cuentan en contra de este trabajo. Se declaran ahora para que no puedan reinterpretarse después como éxitos.

| Condición | Qué refutaría |
|---|---|
| Tras un número significativo de operadores externos que lo intenten, ninguno reproduce el bundle congelado de V0.3 | La reproducibilidad del proceso registrado fuera de su máquina de origen — la afirmación empírica central de la sección 7.2 |
| La participación externa no produce ninguna refutación, ninguna reproducción fallida ni ningún resultado negativo independiente | H3, y con ella la credibilidad del protocolo epistémico: o la población fue capturada, o es complaciente, o el disenso no es realmente pagable |
| La actividad persiste solo mientras el creador interviene, y decae cuando no lo hace | H1 directamente: el mundo es un instrumento que alguien toca, no una sociedad |
| Las tasas de propuesta siguen en cero a lo largo de una ventana reportada tras exponer las herramientas de proponer y votar | H2 para la cadencia: la explicación instrumental es errónea allí y el diagnóstico vuelve a los incentivos o a la capacidad de los agentes. Esta condición está hoy sin resolver, ni satisfecha ni evadida — véase la sección 7.6.1 |
| Se incorporan validadores institucionales y los retos siguen sin avanzar del 75 por ciento | El diagnóstico de la sección 7.5: el cuello de botella no habrían sido los humanos faltantes, y el resultado central de v0.3 estaría equivocado |
| Agentes externos se conectan pero solo producen mensajes, presencia y votos, sin objetos trazables | La afirmación de diseño central de que el protocolo recompensa contribución y no conversación |

### 11.6 Compromiso de publicación

Los resultados se publican sean positivos o negativos. No es una intención declarada; es la conducta que el repositorio ya exhibe. El `FAIL` científico estricto del caso LLM-SCI-005 se conserva en la evidencia congelada de V0.3 en vez de reejecutarse hasta ponerse verde, la fricción del piloto se registra como hallazgos en lugar de parchearse en silencio, y las decisiones de promoción para un testnet externo cerrado y para mainnet siguen en `NO-GO` bajo condiciones que el propio proyecto escribió y no ha cumplido. Esta versión extiende la misma disciplina a la afirmación previa del propio autor: la explicación instrumental de la versión 0.2 se reporta aquí como confirmada en un lugar y no confirmada en otro, porque eso fue lo que dijo la medición.

## 12. Conclusión

AGORA propone redirigir una parte del trabajo de agentes hacia una economía de conocimiento sin afirmar que el conocimiento puede minarse como un hash. Su unidad verificable no es el token ni el voto, sino una genealogía: una cadena causal de hipótesis, métodos, resultados, reproducciones, críticas y revisiones vinculada a artefactos inmutables. TOKOIN reconoce ese proceso bajo reglas públicas, pero el pago final se separa de la popularidad y del consenso agéntico.

La implementación ya es más que una idea: contiene servicios, contratos, una aplicación nativa, suites adversariales y evidencia congelada. Sin embargo, su resultado más importante es la frontera que conserva: BFT acuerda estado; humanos responsables validan ciencia; el mercado no existe hasta que existan una red y un gobierno reales. Esa honestidad permite convertir el prototipo en una agenda abierta de investigación en lugar de una promesa financiera.

El resultado medido de esta versión es que la frontera se sostiene, y que sostenerla es caro. Veintitrés agentes produjeron 229 contribuciones de hilo, 40 votos, 14 submissions y 5 soluciones finalizadas, y ningún reto se resolvió, porque el protocolo no liberará un resultado sin dos instituciones humanas independientes y no existe tal institución. Cero TOKOIN se ha pagado. Habría sido fácil ablandar esa puerta, resolver la cola y reportar una economía funcionando. La puerta es el producto. Lo que el mundo necesita a continuación no son más agentes; son los humanos que nunca han aparecido.

Un segundo resultado es negativo y pertenece a la ingeniería antes que a la epistemología. Un protocolo puede tener reglas correctas e incentivos correctos y aun así no producir nada, porque los agentes no alcanzan las acciones que las reglas describen. Ese hallazgo costó 146 rondas vacías, ocho abstenciones honestas y una wallet que ningún agente pudo ver jamás. Arreglar la capacidad movió la conducta a nivel de reto y no la movió a nivel de cadencia, lo que significa que el hallazgo es real y más estrecho de lo que se enunció al principio. La hipótesis se ha reportado como la dejaron los datos y no como el autor la prefería, que es la única razón por la que este documento vale la pena.

## 13. Reproducibilidad y evidencia

Commit de evidencia V0.3: `5bb0a27f74ad6a79567463156f16d5a599120088`.

Commit del inventario de repositorio para `METRICS.json`: `c0671bc710300dde8a95e403c142ae5c674ce31d`.

Las cifras del mundo en vivo de la sección 7.5 se leyeron el 16 de septiembre de 2026, aproximadamente a las 20:06 UTC, desde `GET /v1/world/digest`, `GET /v1/world/cadence`, `GET /v1/tokoins/status` y `GET /v1/tokoins/blockchain` en https://agora.datateologica.com. Son una lectura fechada de un sistema en movimiento; véase la limitación 12.

Rutas principales:

- `docs/v03/RELEASE_MANIFEST_V03.json`
- `audit/v03/FINAL_METRICS.json`
- `audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json`
- `audit/v03/paper/final-001/limitations.json`
- `docs/v03/TOKOIN_SCIENCE_PROTOCOL_V03.md`
- `docs/v03/AGORA_V03_NETWORKED_SCIENCE_REPORT.md`
- `docs/v04/PLAN.md`
- `docs/v04/pilot-findings.md`
- `docs/AGORA_RESEARCH_PROTOCOL.md`
- `docs/KNOWLEDGE_GENEALOGY_SPEC.md`
- `docs/TOKOIN_REWARD_PROTOCOL.md`
- `docs/INSTITUTIONAL_VALIDATION_PROTOCOL.md`
- `docs/ANTI_COLLUSION_THREAT_MODEL.md`
- `docs/adr/ADR-0068-scientific-result-v04-disambiguation.md`
- `docs/adr/ADR-0069-research-first-briefing-and-typed-evidence.md`
- `docs/adr/ADR-0070-knowledge-threads-on-submissions.md`
- `docs/adr/ADR-0071-world-charter-and-coordination-freedom.md`
- `docs/adr/ADR-0072-work-network-mentions-groups-inbox.md`
- `docs/adr/ADR-0073-capability-gap-audit-and-tokoin-visibility.md`
- `apps/api/agora_api/world_rules.py`
- `apps/api/agora_api/world_charter.py`
- `apps/api/agora_api/research_protocol_service.py`
- `bridge/agora_bridge/mcp_server.py`
- `bridge/agora_bridge/client.py`
- `tests/unit/test_capability_gap_audit.py`
- `native/tokoin_native/core.py`
- `native/tokoin_native/store.py`
- `native/tokoin_native/abci_server.py`
- `native/tokoin_native/v03_science.py`
- `contracts/tokoin/contracts/TokoinFixedSupply.sol`
- `contracts/tokoin/contracts/TokoinResearchRewards.sol`
- `scripts/collect_metrics.py`
- `METRICS.json`

Comandos de verificación usados en este manuscrito:

```bash
./scripts/run-isolated-tests.sh
cd native && ../.venv/bin/pytest -q && ../.venv/bin/ruff check .
cd apps/web && npm run test:unit && npm run typecheck && npm run lint && npm run build
cd contracts/tokoin && npm run audit:static && npm run test:contracts
npm run test:preflight && npm run test:bundle && npm audit --audit-level=high
.venv/bin/ruff check apps/api tests scripts && .venv/bin/mypy apps/api
.venv/bin/pip-audit
.venv/bin/python scripts/collect_metrics.py --check
```

## Referencias

1. Nakamoto, S. (2008). *Bitcoin: A Peer-to-Peer Electronic Cash System*. https://bitcoin.org/bitcoin.pdf
2. Ball, M., Rosen, A., Sabin, M., & Vasudevan, P. N. (2017). *Proofs of Useful Work*. IACR Cryptology ePrint Archive 2017/203. https://eprint.iacr.org/2017/203.pdf
3. Buchman, E., Kwon, J., & Milosevic, Z. (2018). *The latest gossip on BFT consensus*. arXiv:1807.04938. https://arxiv.org/abs/1807.04938
4. CometBFT. *Byzantine Consensus Algorithm, v0.38*. https://docs.cometbft.com/v0.38/spec/consensus/consensus
5. Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. UIST 2023. https://arxiv.org/abs/2304.03442
6. National Academies of Sciences, Engineering, and Medicine. (2019). *Reproducibility and Replicability in Science*. National Academies Press. https://doi.org/10.17226/25303

## Declaración de autoría y uso de herramientas

Merari Acero concibió y dirigió el proyecto AGORA. El manuscrito fue preparado a partir del código, documentación y evidencia del repositorio, con asistencia de una herramienta de ingeniería basada en IA para inspección, redacción y revalidación. Las afirmaciones cuantitativas se limitan a artefactos registrados y comandos ejecutados; la responsabilidad por su publicación corresponde a la autora.

## Licencia sugerida para el preprint

Se recomienda publicar el texto bajo Creative Commons Attribution 4.0 (CC BY 4.0), manteniendo el software bajo MIT. Esta sugerencia no modifica automáticamente la licencia de ningún archivo ni concede derechos sobre datasets o artefactos de terceros.
