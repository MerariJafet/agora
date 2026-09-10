# Segunda iteración — mejoras derivadas de resultados

Entrada: ../iteration-1/RESULTS.md, SHA-256 `9ef2c822cef54ccd35c829c77f5569a68cda5276a56c4c2892791e1e19c5c1cb`.

Objetivo: resolver los cinco hallazgos anteriores preservando política monetaria y motor CometBFT. Implementar contrato explícito python-scripted-test y ciclo científico completo aislado; CLI de wallet segura; errores reales de SQLite y pruebas de atomicidad; propuestas inválidas y recuperación en red; CI y guías de operación.

Verificación: repetir suite nativa completa y 100,000 secuencias en directorio nuevo; suite científica vía run-isolated-tests.sh; campaña de caos separada con hashes de fuente/configuración; compilación/ejecución limpia con versiones fijadas. Registrar cualquier fallo inicial y corrección. No sobrescribir evidencia previa ni usar resultados históricos como resultado del candidato final.

Cierre: matriz requisito→evidencia→limitación, informe consolidado y decisión separada para laboratorio, publicación metodológica, testnet externa y mainnet. Las máquinas e instituciones independientes son dependencias externas, no se simulan como independencia real.
