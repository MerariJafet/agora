# Descubrimiento y decisiones previas — 2026-09-09

Estado: diseño incremental aprobado internamente para implementación local; NO autorización de mainnet. Base inspeccionada: HEAD 717bf39627502e96a4c9e2a21a7f9a34cb6d4c63 con cambios previos sin commit que se preservan.

## Arquitectura observada

- API FastAPI/SQLAlchemy, PostgreSQL científico, Redis, NATS/outbox, Bridge Python y web Next.js. Conservar identidad AGORA, dispositivos Ed25519, sesiones, artefactos, eventos, retos y agentes.
- `tokoins_service.py`: 8 decimales, 1M TOKOIN preasignado a tesorería, proyecciones de wallet, asientos hashados, bloques de transparencia; no consenso P2P. Direcciones tkw1 derivadas de identificadores, no de una clave monetaria independiente. No reutilizar como fuente monetaria nativa.
- `contracts/tokoin`: ERC20 con preminado completo en constructor, identidad, control plane, recompensas, verificadores y pruebas. Mantener compatibilidad como legado; ninguna conversión implícita ni despliegue Base como destino final.
- `models.py`: TokoinSupply/Wallet/LedgerEntry/Block/TransactionAuthorization; ResearchCandidateSnapshot/Institution/InstitutionalReview/RewardCalculation/PublicationPackage; InstitutionalValidator y asignaciones sintéticas; MagnaKnowledgeObject/Edge; reservas y snapshots de migración existentes. Conservar todas estas tablas.
- `research_protocol_service.py`: snapshots/genealogía, scoring explicable, reparto 1/10/60/20/9, revisión de propietarios, bloqueo provisional y exportación. `institutional_validator_service.py`: revisión TEST, conflictos, commit/reveal y paneles. No confundir estas pruebas con credenciales reales.
- Pruebas existentes unitarias/integración/seguridad/E2E y pruebas EVM. Ejecución de pruebas API mediante scripts/run-isolated-tests.sh. Nuevas pruebas nativas sin tocar DB o credenciales AGORA.

## Resoluciones de consistencia

1. Reutilizar ACEROS = 10^8; toda cantidad monetaria entera estricta (rechazar float y bool). MAX = 10^14 unidades inalterable por transacción.
2. Un nuevo protocolo `TOKOIN_NATIVE_REWARD_V2` separa el reparto 10/10/51/20/9 del V1 histórico. Nunca recalcular asientos anteriores silenciosamente.
3. Supply inicial cero. El saldo bloqueado cuenta como creado. Revocado se retira del saldo, pero continúa consumiendo el límite acumulativo de creación: no existe reciclaje que viole `TOTAL_CREATED`. Es una decisión conservadora explícita.
4. Límite piloto acumulativo de creación 500 × 10^8, más estricto que sólo limitar finalización. Rechazar reservas por encima evita prometer rewards imposibles de pagar. No quemar/redimensionar automáticamente una autorización.
5. TEST es un dominio de cadena separado y no genera derechos económicos. Un manifiesto TEST nunca es candidato económico de mainnet. El piloto reconocible exige credenciales institucionales reales y evidencia verificable. No ascender saldos internos históricos por su mera existencia.
6. Dos instituciones no garantizan verdad; son el umbral de un procedimiento. Su identidad e independencia requieren acreditación externa. Sus firmas no pueden escoger cualquier supply: monto y reparto deben satisfacer política determinista versionada.
7. Una impugnación admitida con dos firmas pausa el reloj; una denuncia presentada permanece en la historia sin bloquear la finalidad. El rechazo o una corrección menor reanuda el contador con los segundos consumidos intactos; revisión material revoca la autorización anterior y exige candidato/version/revisión nuevos con 365 días completos. La creación gastada anterior no se reutiliza. Una revisión invalidada después de finalización cambia el conocimiento, no confisca dinero.
8. Finalidad de bloques BFT separada de maduración científica. Tiempo de pruebas puede simular 365 días; nunca presentarlo como maduración real. Se seleccionó CometBFT y se preparó el adaptador ABCI; no se desarrolla un consenso nuevo.
9. El génesis canónico compromete política, registro institucional, identificador de cadena, dominio y conjunto inicial de validadores blockchain; `InitChain` comprueba este último. Debe fijarse también el hash del génesis CometBFT completo. El prototipo se limita a TEST; génesis económico requiere pruebas externas, política de autorización, snapshot verificado y operadores independientes.
10. Pagar revisores sólo de investigaciones aprobadas deja un incentivo residual: el pool debe reconocer revisiones adversas de versiones anteriores; financiación de investigaciones definitivamente rechazadas queda abierta y no se resuelve con emisión arbitraria.

## Cambios de modelo

Añadir módulo nativo aislado con transiciones deterministas, recompensas versionadas, nonces, balances propios y registro de bloques; jamás autorizar balances desde SQL. Proyecciones futuras: `chain_id`, `height` y `state_root`, dirección de fondos separada de `agent_id`, `reward_id` y compromisos científicos. No ejecutar migración destructiva. La API científica produce un paquete, no escribe saldos nativos. El adaptador valida hashes, firmas y versión antes de proponer una transacción. El explorador se alimenta de estado verificado del nodo.

## Secuencia y pruebas de aceptación

A. Diseños monetario/consenso/amenazas/migración y simulación de tres modelos antes de seleccionar monto experimental.
B. Núcleo determinista y firmado: emisión, reparto ponderado, lock, challenges, finalización, transferencia, caps, replay, duplicados, firmas, falsos validadores y determinismo.
C. Persistencia atómica/replay desde génesis, verificación independiente, exportación de compromisos y manifiesto determinista.
D. Engine CometBFT + adaptador ABCI, cuatro nodos y fallos/particiones/sync. Verificar software instalado y versiones. Un replay en tres procesos no es una prueba P2P.
E. Adaptador AGORA/credenciales institucionales, UI/explorador y piloto aislado. Ninguna prueba debe atribuir resultados sintéticos a universidades reales.
F. Piloto reconocido/maduración real y génesis económico requieren evidencia externa; no pueden darse por terminados acelerando un reloj de pruebas.

## Actualización de consistencia tras revisión adversarial

La raíz Merkle nativa de versión 2 compromete el número de hojas. El estado inicial incluye los validadores de consenso y ABCI verifica su correspondencia durante el arranque. Sólo una admisión institucional de dos firmas pausa la maduración; presentar hashes por sí solo no congela una recompensa. Persiste el riesgo de censura de denuncias válidas antes de su admisión, que requiere evidencia disponible, plazos y apelación antes de uso económico. La finalidad no permite confiscación retroactiva.

La matriz de aceptación en `TOKOIN_MAINNET_READINESS_CHECKLIST.md` distingue implementación local, integración parcial y dependencias externas. Ni los validadores TEST ni un manifiesto local sustituyen instituciones reales, maduración económica o un génesis de producción verificado.
