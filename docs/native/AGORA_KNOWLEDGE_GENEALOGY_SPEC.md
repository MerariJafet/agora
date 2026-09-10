# Genealogía del conocimiento

La fuente científica sigue siendo AGORA: `MagnaKnowledgeObject`, sus relaciones, los artefactos versionados y `ResearchCandidateSnapshot`. Se reutilizan la exportación de preimágenes, los hashes, la raíz congelada, la autoría y las relaciones existentes. No se crea un segundo grafo ni se sobrescribe la historia para adaptar una recompensa.

Una corrección material produce una nueva versión del candidato. Las revisiones y autorizaciones anteriores permanecen enlazadas a la versión que evaluaron. Los tipos de nodo o relación adicionales del plan maestro necesitan un mapeo explícito al esquema real; este prototipo no implica que todos ellos estén implementados.

La cadena conserva compromisos: investigación, versión, raíz de genealogía, hashes del paper, datos y código, autorización y revisiones. Los documentos completos permanecen en almacenamiento verificable. Su disponibilidad y reproducción se comprueban fuera del consenso blockchain; un hash correcto no garantiza que los bytes estén disponibles ni que la conclusión sea válida.

Se reutilizan `scripts/verify_research_package.py` y `agora_api.research_export.verify_package` para comprobar integridad contra un compromiso confiable. Esas comprobaciones no ejecutan el experimento ni acreditan corrección científica. Un expediente incompleto se rechaza o recibe un dictamen de evidencia insuficiente; nunca se completa con resultados inventados.

La función Merkle nativa usa un compromiso de raíz de versión 2 que incorpora el número de hojas. Así distingue una lista de otra obtenida duplicando su última hoja. Los consumidores deben verificar también el orden canónico y la versión del compromiso; no deben reinterpretar raíces históricas con reglas nuevas.
