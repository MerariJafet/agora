# Matriz de afirmaciones publicables

Estado: borrador interno, no enviado a revista, universidad ni registro. Autoría humana, licencia, revisión externa, decisión de divulgación/IP y related work sistemático pendientes. No se afirma patentabilidad ni prioridad legal.

| Afirmación | Evidencia exigida | Alcance |
|---|---|---|
| Separación de consenso BFT y revisión científica | Código ABCI/core y paquetes SCI | Implementación local; no consenso científico como verdad |
| Cap1M y500TEST | Campañas monetarias seed20260909, tests frontera | Propiedad del corpus/versión; no prueba formal de ausencia de bugs |
| Reproducción de100000secuencias | iteration-comparison.json | Dos corridas del mismo corpus, no200000casos independientes |
| Tolerancia a fallos/particiones | Cada report de chaos con mismoheight/AppHash | Procesos de unPC, bajo supuestos BFT; no descentralización real |
| Double-sign detectable | Evidencia firmada real y presencia en bloque | No demuestra slashing ni castigo económico |
| Maduración365d | ProtocolTime/fronteras/reinicio/replay | Tiempo simulado de aplicación; no año real ni tokens convalor |
| Seis escenarios científicos | APIaislada, workersPython, manifests/reviews/replay | Ejecución computacional sintética, no universidades niLLMautónomos |
| Wallet cifrada y rechazo replay | Suitewallet/CLI/TXV3 | ClavesTEST, amenazas ensayadas; no auditoría independiente |
| Binario repetible | clean-build-result.json | MismoPC con inputs descargados reutilizados |

No demostrado: adopción universitaria, verdad general, novelty científica del diseño, economía sostenible, demanda/valorTOKOIN, admisiónpermissionless, Sybilresuelto, resistencia completa a censura, mainnetsegura, compensación negativa independiente y operación en máquinas externas.

La contribución candidata del paper es una arquitectura implementada y su evaluación adversarial reproducible. El motor se atribuye explícitamente a CometBFT, que implementa replicación BFT de máquinas de estados; no se reclama haber inventado su consenso. Fuente oficial consultada: https://docs.cosmos.network/cometbft/latest/docs/README. El código fijado de0.38.26 prevalece para métodos/versiones específicas.
