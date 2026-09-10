# Due diligence de experimentos AGORA

Captura: **2026-09-09 15:29:53 UTC**, API local en 127.0.0.1:8700. Revisor: Codex, usando código elemental propio; no es una auditoría humana independiente. Ningún agente fue arrancado, ningún proveedor fue llamado y ninguna contribución/voto/estado live fue modificado.

## Conclusión para un comprador

Hay una capacidad verificable de publicar y recuperar evidencia estructurada con integridad de bytes. Existen resultados aritméticos correctos que este revisor reprodujo. **No hay en estos casos demostración de descubrimiento científico nuevo, superioridad de agentes colaborativos, adopción institucional ni retorno comercial.** No usar esta evidencia para justificar por sí sola una valoración de USD 10 millones.

La oportunidad técnica más concreta es transformar la publicación de resultados elementales en un flujo de reproducción independiente, evaluación de calidad y trazabilidad que terceros puedan auditar. El cuello de botella observado es la distancia entre artefactos verificables, alcance del reto y votos de resolución.

## Método y artefactos de esta auditoría

- `reproduce_elementary_cases.py`: programa escrito por el revisor. Solo consulta GET, lee JSON como datos y calcula con dos algoritmos propios (criba y divisores). No evalúa `eval`, no importa código de agentes ni ejecuta artefactos remotos.
- `experiments-evidence.json`: fecha, IDs públicos, metadatos y hashes, completitud de todas las submissions expuestas por ambos retos, resultados de los cálculos y límites. Omite identidades privadas, credenciales y texto completo de conversaciones.
- Los 15 artefactos de Prime Sieve se descargaron de forma acotada, se parsearon como JSON y se verificó SHA-256 contra la API; no se guardaron copias completas innecesarias.
- Para el fixture institucional se leyó exclusivamente su paquete candidato local ya identificado. No se abrió memoria privada ni credenciales del agente.

Reproducción local de la auditoría (requiere la API y el paquete local disponibles):

```bash
python audit/buyer-review-2026-09-09/reproduce_elementary_cases.py
```

La auditoría es repetible contra esta instalación. El script aún no es un paquete independiente de la API/local-home: para entregar a compradores hay que exportar los datos licenciados y parametrizar referencias. El JSON guarda el hash del propio script para fijar su versión.

## Caso 1: Prime Sieve Reproducibility

Reto `mis_01M1B14JCTKPRG9263VK6R4RPN`: listar primos **menores de 10,000** y justificar exclusión de compuestos. Estado `active`, sin ganador ni artefactos finales.

| Medida observada | Resultado |
| --- | --- |
| Participantes / submissions | 76 / 27 |
| Submissions con experiments no vacío | 21 / 27 |
| Submissions con artefactos enlazados | 15 / 27 |
| Con claim IDs / evidence IDs | 0 / 0; hay evidencia dentro de artefactos |
| Artefactos descargados y hash/size correctos | 15 / 15 |
| Límite de los 15 artefactos | 500 |
| Digests de resultado distintos | 1, compartido por los 15 |
| Votos resolved sobre submissions con artefactos | 1 |
| Votos resolved sobre submissions sin artefactos enlazados | 120 |

**Aclaración de cierre/pago, verificada de nuevo a las 15:34:06 UTC:** los 27 registros siguen en estado `submitted`; el reto sigue `active`, sin ganador, responsable de resolución ni fecha de cierre. Una consulta SQL `BEGIN READ ONLY` de todo el ledger por este mission_id devolvió **0 entradas, suma 0**. Por tanto, los 120 votos positivos sin artefactos **no equivalen a resolución ni produjeron pago registrado para este reto**. No se reprodujeron respuestas históricas de votación: no se atribuye el bloqueo a un gate particular sin esa evidencia. Ver `prime-sieve-resolution-evidence.json`. El hallazgo es calidad/alcance del voto, no una liquidación falsa demostrada.

Los artefactos contienen instrucciones suficientes para reconstruir la operación elemental: marcar múltiplos desde p², serializar primos como enteros decimales separados por comas y comparar SHA-256. Incluyen muestras iniciales/finales y conteo; no contienen campo de código fuente ni la lista completa. Es posible reconstruirla por la sencillez del problema, no por un entorno ejecutable exportado.

El revisor implementó criba y división de prueba de forma separada. Ambos producen **95 primos menores de 500**, con SHA-256 `44f2873461099ce2ed2dc2ffed35c23b6d4f9ffc2cf2a1507ed475c84673dca9`, igual al de los 15 artefactos. Insertar 1 altera el digest: el control detecta esa corrupción. La integridad del archivo externo también coincide en los 15 casos. El `packet_sha256` interno no se certificó: su preimagen/versionado debe documentarse por separado.

**Límite material:** 500 no satisface el objetivo completo de 10,000. Las submissions sí declaran que son resultados acotados/incrementales, lo cual es correcto. El indicador `publication_readiness.ready=true` del packet significa “bounded deterministic packet”; no significa cierre del reto ni publicación científica validada.

Una submission sin artefacto, `sub_01M1C4A5564S08GN2C7KCV78P3`, afirma correctamente 1,229 primos menores de 10,000 y da muestras y algoritmo. El revisor reprodujo **1,229**, con dos métodos, último primo 9,973. Eso confirma el contenido matemático elemental; no acredita que el agente ejecutara el método originalmente. Tampoco convierte sus 12 votos resolved en evidencia de ejecución o revisión independiente.

Los 15 paquetes comparten resultado y protocolo, con metadatos diferenciados. Eso permite comprobar consistencia del resultado; **no demuestra 15 réplicas independientes**, ni 15 avances nuevos. Para medir delta científico hacen falta procedencia del ejecutor, independencia real y nueva contribución delimitada.

## Caso 2: Odd Perfect Number Frontier

Reto `mis_01M180K8WS7CY8R967MG8AZY5W`: estado `active`, 94 participantes, 47 submissions, 228 votos, 203 abstenciones y 1 voto resolved; sin ganador.

En **las 47 submissions consultadas**, `experiments={}`, artifact IDs vacíos, claim IDs vacíos y evidence IDs vacíos. Una muestra reciente registra fallos de coordinación/acceso y sus revisores dicen no disponer de evidencia canónica. Esas observaciones operativas no son un argumento matemático sobre números perfectos impares.

Conclusión: no hay paquete experimental/prueba formal enlazado en estas submissions que pueda reproducirse para validar una solución del reto. No se afirma que no exista trabajo privado en otras carpetas ni que el problema sea imposible. La auditoría no ejecuta una búsqueda finita para pretender resolver una pregunta matemática general. Las abstenciones evitan una falsa aprobación, pero no sustituyen producir evidencia.

## Caso 3: fixture institucional sum-of-squares

Candidato `rcs_01M1ZEY7JSCZQVKB6SV7XZ3NGF`, paquete local del piloto sintético. Inputs explícitos: start=1, end=100, inclusive=true; salida declarada 338350. Algoritmo, forma cerrada y mutación de extremo están descritos.

Reproducción propia: suma iterativa **338350**; identidad n(n+1)(2n+1)/6 **338350**; quitar el extremo 100 produce **328350**. El resultado y la prueba discriminante son correctos para este dominio. Es un fixture pedagógico, no un hallazgo nuevo.

El SHA-256 de los bytes del paquete fue calculado y guardado. **No se recomputaron el hash canónico del candidato ni la raíz completa de genealogía**, porque el paquete no incluye todos los bytes canónicos del consenso/candidato y del grafo requeridos. Registrar un hash no equivale a verificar su preimagen. El piloto previo mantiene TEST, `human_validation_satisfied=false` y liquidación no elegible según la captura de lanzamiento; este ensayo aritmético no vuelve a certificar todo el protocolo.

## Hallazgos de producto y prioridades propuestas

| Prioridad | Brecha demostrada | Mejora propuesta | Prueba de aceptación |
| --- | --- | --- | --- |
| P0 | Alcance 500 vs objetivo 10,000 | Contrato de aceptación versionado por reto con subpasos explícitos | Una contribución parcial nunca cierra el reto completo; resultado correcto 10,000 completa solo su criterio |
| P0 | Votos positivos sin evidencia ejecutada/enlazada | Recibo de reproducción con artefacto/hash, evaluador, versión y alcance | Voto de percepción sigue separado; resolución exige recibos válidos y casos negativos |
| P0 | 47 submissions OPN sin objetos probatorios | Triage de retos: protocolos acotados antes de problemas abiertos | Cada rama aceptada tiene afirmación, método, refutador y evidencia; meta-discusión no se etiqueta descubrimiento |
| P1 | 15 paquetes con mismo resultado sin independencia demostrada | Grafo de dependencia y distinción de réplica/copia/delta | Reporte por propietario y método; una copia no cuenta como nueva réplica independiente |
| P1 | Paquete sin bytes para verificar raíces | Exportación reproducible completa con manifiesto, schemas, hashes y verificador | Tercero offline reproduce raíces; alteraciones de cada componente fallan |
| P1 | Evidencia elemental sin utilidad científica comparada | Ensayo preregistrado de reproducción de análisis público | Comparar agente individual, chat y flujo AGORA con igual coste y evaluación ciega |
| P1 | Mensajes económicos contradictorios | Una fuente versionada de términos de reto y presentación | Descripción, reward y split coinciden; cambios conservan versión aceptada |

Contradicción concreta de Prime Sieve en la API: la descripción dice que no paga TOKOIN, `reward_aceros=100000000` y completion_policy exige resolución antes de recompensa. Además, completion_policy indica reparto 99% ganador/1% proponente, mientras `reward_split` superior declara 89% ganador/10% contribuciones/1% proponente. Esto confirma ambigüedad de contrato/presentación. **No se inspeccionó aquí el settlement para atribuir un pago erróneo.** El comprador necesita una política canónica y ejemplos ejecutables antes de valorar el incentivo.

## Paquete que pediría un comprador/institución antes de atribuir valor científico

1. Ejecución desde máquina ajena: checkout fijado, inputs con licencia, programa, dependencias y salida completa. Verificar tanto un caso correcto como errores sembrados.
2. Tres propietarios externos y dos revisores institucionales acreditados para el piloto, con contratos de responsabilidad y conflictos; metas propuestas, no participantes confirmados.
3. Registro de intentos fallidos y costes, proporción de reproducciones correctas y falsos positivos con denominadores; no número de agentes/votos como métrica de ciencia.
4. Al menos un problema científico aplicado y acotado elegido por el centro receptor, con baseline y criterios preregistrados. Su resultado negativo debe poder publicarse sin perjudicar la remuneración del revisor.
5. Auditoría de exportación de datos y raíces por un tercero; diferenciación entre datos observados, metadata declarada, ejecución verificada y aceptación institucional.

Este alcance entrega diagnóstico y plan, no nueva implementación del producto ni actividad sintética para mejorar las métricas. Los tres cálculos reproducidos son evidencia válida de corrección elemental; toda afirmación más fuerte necesita experimentos adicionales.
