# Matriz de requisitos y cobertura

PASS se refiere al ensayo identificado. PARTIAL no equivale a que el requisito completo esté resuelto. Los resultados de la copia congelada se incorporan al informe final.

| Área | Implementación y evidencia | Estado del alcance solicitado |
|---|---|---|
| WS-01 Tiempo | ProtocolTime, unlock_at, AST/CI, fronteras y replay; time-audit.json | PARCIAL: reloj completo de un validador no virtualizado |
| WS-02 Firmas/nonces | TX V3, canonical, 128 consultas concurrentes, fuzz | PASS en suite local |
| WS-03 Estado/journal | durable_head, hashes, 12 puntos de crash, corrupción, clone limpio | PASS local; máquina de tercero pendiente |
| WS-04 Consenso/caos | Cuatro motores, particiones, propuesta inválida, doble firma, netem, sync | PASS de escenarios documentados; alcance temporal completo pendiente |
| WS-05 Wallet | Cifrado, red vinculada, backup, CLI, interrupción, secretos | PASS de ensayos y escaneo acotado |
| WS-06 Moneda | 100,000 secuencias repetidas, referencia entera, caps y residuos | PASS del corpus; no prueba exhaustiva |
| WS-07 Ciencia | Seis SCI por API y protocolo nativo; revisión ciega y replay | PARCIAL: trabajadores Python, puente de aplicación y pago negativo pendiente |
| WS-08 Abuso | Duplicados, voto propio/repetido, apelación acotada, señales REVIEW_ONLY | PARCIAL: Sybil, colusión oculta, citas falsas y censura no resueltos |
| WS-09 Revocación | Antes de madurez revoca; después informa sin confiscación; explorer | PASS TEST; economía posterior mainnet pendiente |
| WS-10 Evidencia | Logs, hashes, semillas, fallos previos, código congelado e índice | PASS local; sin atestación independiente |
| WS-11 Operadores | Ocho guías y TESTNET_MANIFEST | PREPARADO; validación por terceros pendiente |
| WS-12 Publicación | Claims acotados, fuente congelada y resultados verificables | BORRADOR INTERNO; publicación/IP/autoría pendientes |

## Correspondencia de pruebas obligatorias

- TIME-001: `test_time_guard_aliases_and_dynamic_access` más inventario y revisión del adaptador. Garantía limitada al alcance first-party indicado.
- TIME-002: `test_conflicting_height_and_backward_time_rejected`.
- TIME-003 a TIME-006: `test_persisted_unlock_boundaries`.
- TIME-007 y TIME-008: votos ±60s en red; **PARTIAL**, no reloj integral.
- TIME-009: `test_restart_at_unlock_and_replay_cannot_double_finalize`.
- TIME-010: replay de Store, expedientes SCI y exports de nodos.
- TX-001: `test_signature_replay_cross_chain_atomic` y corpus monetario.
- TX-002, TX-014: `test_128_concurrent_duplicate_nonces_settle_only_once` y commit concurrente.
- TX-003 a TX-010: `test_transaction_all_domains`, `test_same_chain_different_genesis_replay_regression`, firma alterada y corpus.
- TX-011 a TX-013: fuzz, JSON profundo, codificación alternativa y límite de bytes.
- STATE-001/002/010: replay de journals y AppHash por altura en red.
- STATE-003: `test_real_crash_points` y `test_mid_transaction_crash_replays_committed_only`.
- STATE-004 a STATE-007: daño de journal y tamper; límites de reconstrucción documentados.
- STATE-008: cuatro stores y dos órdenes de operaciones independientes producen AppHash idéntico (order-permutation-replayable.json). Orden canónico probado además mediante serialización y validación secuencial. No se afirma conmutatividad de transacciones dependientes; su orden legítimamente cambia el estado. Cobertura de permutaciones independientes limitada.
- STATE-009: copia limpia y entorno nuevo en este PC; **no máquina externa**.
- BFT-001 a BFT-013 y BFT-015: escenarios con esos IDs en report.json de la campaña completa.
- BFT-014: cortes TCP en campaña completa y pérdida IP en campaña netem; no se confunden ambos mecanismos.
- WALLET-001 a WALLET-006: `test_wallet_hardening.py`; incorrecta contraseña, corrupción, truncamiento, restauración, identidad y red.
- WALLET-007: secret-audit.json y pruebas de no exposición; recetas de claves TEST públicas declaradas.
- WALLET-008: proceso terminado antes/después de publicación atómica y fallo fsync.
- SCI-001 a SCI-006: directorios separados del run científico; saldos SQL vivos no participan.
- REV-001/002: challenge del día 364 y fronteras/reinicio de madurez.
- REV-003/004: `test_post_maturity_invalidation_never_claws_back`, incluye transferencia previa.
- REV-005: rechazo de challenge conserva maduración.
- REV-006: duplicados y apelación acotada; no demuestra resistencia a todos los ataques coordinados.

## Condiciones pendientes y criterio de cierre

1. Reloj completo de un validador: entorno por máquina/proceso que altere realmente todas sus lecturas sin tocar el host; demostrar seguridad/liveness y conservar configuración. Los votos modificados no sustituyen esto.
2. Ciencia autónoma y asentamiento por red: ejecutar una cohorte declarada de agentes, publicar paquetes verificables, enviar autorizaciones por cliente a CometBFT y comprobar provenance en explorer. La simulación de 365 días sigue aislada y sin valor.
3. Pago de revisión negativa: especificar fuente y criterio compatibles con cap y recompensas por conocimiento. No introducir emisión arbitraria o modificar el reparto congelado para cerrar una casilla.
4. Censura/plagio/citas: corpus adversarial de supresión, referencias existentes que no sustentan claims y colusión; falsos positivos medidos y apelación independiente.
5. Operadores externos: claves propias, equipos y redes administrativas separadas, guías verificadas por terceros y nueva campaña de partición/restart/sync.
6. Publicación: revisión de afirmaciones, related work, responsabilidad humana y decisión de divulgación. No se presume autorización externa, colaboración universitaria ni valor económico.
