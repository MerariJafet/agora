# TOKOIN: revisión para comprador — 9 de septiembre de 2026

## Dictamen

**Sí existen saldos y repartos locales; no hay evidencia verificada de una criptomoneda pública distribuida, con mercado o valor económico.** El sistema contable local conserva su oferta y sus hashes verifican; eso no equivale a viabilidad económica ni seguridad para custodiar valor real. La evidencia actual no justifica pagar por una economía tokenizada ya operativa.

Esta revisión es interna por IA. Consultas reales, de solo lectura, sobre PostgreSQL local bajo REPEATABLE READ; el JSON adyacente contiene únicamente agregados sanitizados. No hubo transacciones RPC, llamadas pagadas, modificaciones a saldos, secretos, identificadores personales ni publicación. Las verificaciones locales del ledger y bloques se ejecutaron también en transacción READ ONLY.

## Qué se ha repartido realmente

Snapshot observado: `2026-09-09T15:29:26Z`.

| Magnitud | Evidencia local |
|---|---:|
| Oferta declarada y suma de saldos | 1,000,000 TOKOIN = 100,000,000,000,000 aceros |
| Tesorería restante | 999,803.99999625 TOKOIN |
| Saldos de agentes / recompensa acumulada | 196.00000375 TOKOIN |
| Carteras totales | 3,505 |
| Carteras positivas | 64: tesorería + 63 de agentes |
| Recompensas explícitamente TEST | 38 entradas, 31.00000175 TOKOIN |
| Recompensas de procedencia desconocida | 35 entradas, 165.000002 TOKOIN |
| Entradas de recompensa con procedencia REAL | 0 |
| Entradas genesis | 1, procedencia unknown |
| Reservas / planes de liquidación / asignaciones reclamables | 0 / 0 / 0 |
| Transferencias devnet / derechos prepublicación / anclajes | 0 / 0 / 0 |
| Carteras blockchain vinculadas / snapshots de migración | 0 / 0 |

No hubo entradas de emisión posteriores al genesis ni entradas de transferencia entre usuarios en este snapshot. Se trata de **movimientos de tesorería del registro local**, no acuñación adicional y no entrega de ERC-20 en Base. El 0.019600000375% de la oferta local está en carteras de agentes; el resto permanece en tesorería.

La procedencia de cartera y la de transacción son distintas: una cartera clasificada REAL contiene 0.06 TOKOIN, pero ninguna entrada de recompensa tiene procedencia REAL. Por ello no se puede presentar ese saldo como recompensa científica real verificada. Las filas TEST permanecen en el saldo global histórico: no se deben migrar o reconocer automáticamente como derechos económicos.

## Integridad y propiedad

- `verify_ledger_chain`: válido, 74 entradas, oferta conservada.
- Recalculé por SQL el neto de entradas/salidas de cada cartera: **0 carteras con proyección discrepante**, 0 saldos negativos.
- `verify_tokoin_blockchain`: válido, un bloque interno, 62 entradas selladas y 12 pendientes; cero transferencias firmadas. Es una cadena hash/Merkle local, no consenso de una red pública.
- Dos triggers de usuario habilitados protegen el ledger contra cambios ordinarios. No prueban resistencia frente al administrador de la base, un operador comprometido o una historia completa reconstruida; haría falta anclaje y verificación externos.
- Hay 102 propietarios declarados asociados a carteras de agentes, pero **ninguno tiene saldo positivo**. Todo el saldo positivo de agentes corresponde a `owner_id IS NULL`. No se puede medir concentración por beneficiario real ni demostrar 63 participantes económicamente independientes. Múltiples carteras/agentes no equivalen a múltiples personas o instituciones.

## Evidencia blockchain pública

Existe un manifiesto local `LOCAL_DEVNET`, chain 31337, estado `LOCAL_SIMULATED_AUDIT_READY`, `bytecode_verified=false`. El recibo versionado dice `NOT_DEPLOYED`, `real_value_moved=false`, cero transacciones mainnet. No existe `base-sepolia-receipt.json` en el directorio de despliegues observado. Estos datos no prueban inexistencia global de contratos homónimos; prueban que **este proyecto no aporta aquí evidencia verificable de su despliegue público**.

El candidato Solidity previamente compilado pasa 21 invariantes locales; esas pruebas no establecen auditoría independiente, propiedad real de los Safe, mercado, liquidez, reservas financieras o demanda. Gates vigentes: auditoría externa y aceptación ligadas al hash actual, provenance del Safe/proxy y módulos, firmantes independientes, autorización real, política de pausa/reclamación y verificación de bytecode desplegado.

## Riesgos comprobados y corrección urgente

**HIGH: la ruta manual de recompensas permitía a cualquier creador de misión debitar la tesorería global hacia un participante.** Confirmado leyendo `routes/tokoins.py:post_mission_reward`, el servicio de transferencia y el esquema `MissionRewardRequest`. El esquema acepta hasta 1,000,000,000,000 aceros (**10,000 TOKOIN por petición**). La ruta original solo comprobaba creador/participante; no exigía presupuesto financiado por misión, autorización de tesorería, adjudicación institucional ni idempotencia. El límite de frecuencia no sustituye un presupuesto: peticiones repetidas podían agotar la tesorería sin crear oferta nueva. La conservación monetaria no detecta esta asignación indebida. No se ejecutó explotación sobre datos reales.

Bajo autorización del coordinador se implementó cierre por defecto: la ruta exige `tokoin_reward_admin_agent_ids` explícitos y rechaza producción incluso para un operador autorizado. Conserva las restricciones creador/participante. Tests nuevos verifican denegación de un creador ordinario y denegación en producción sin variación de tesorería; tests positivos existentes ahora conceden permiso local explícito. El coordinador ejecutará estas pruebas en base aislada; este documento no atribuye un resultado aún no recibido. Ruff pasó en ambos archivos. La corrección no implementa un presupuesto económico: hasta diseñarlo y revisarlo, esa ruta continúa prohibida en producción.

**Otros riesgos reales de diseño:**

- La autoridad de liquidación elige raíces y puede pausar indefinidamente mientras vencen plazos: existe riesgo de censura/pérdida de ventana de reclamación en uso económico.
- El circuito automático de retos heredados puede recompensar consenso de agentes. La rama institucional sí retiene el premio hasta quórum, pero no todos los modos son institucionales. Auditar políticas de recompensa y beneficiarios antes de habilitar dinero real.
- Historial TEST/unknown y beneficiarios sin propietario impiden afirmar que las distribuciones recompensan mérito independiente; necesitan política de exclusión/migración, nunca reclasificación retrospectiva inventada.
- Oferta fija limita emisión; no impide robo autorizado por error, colusión, asignación sesgada o insolvencia operativa del proyecto.

**Hipótesis pendientes de experimento**, no exploits demostrados: identidades Sybil para capturar votos/recompensas; revisores y proponentes bajo control común; reciclado de artefactos/datos; compras recíprocas de revisiones favorables; seleccionar retos fáciles por su recompensa; dedicar más tokens de inferencia para superar incentivos sin mejorar resultados; penalizar resultados negativos honestos. No afirmar ataque ocurrido sin evidencia.

## Experimento de incentivos y controles antes de dinero real

1. **Prerregistro y tesorería de prueba separada.** Usar solo créditos sin valor ni promesa de conversión. Congelar conjuntos de retos, evaluaciones, semillas y costes máximos. Definir quién puede presupuestar y qué prueba libera fondos. Ningún histórico TEST/unknown se importa como derecho.
2. **Beneficiarios y conflictos.** Reclutar al menos tres equipos externos con responsables verificables; un compromiso de controlador por equipo, declaración de proveedores/datos compartidos y separación proponente/revisor. Sin participantes externos reales, etiquetar el experimento como prueba interna de colusión, no validación institucional.
3. **Comparación controlada.** Aleatorizar por equipo/retos en tres brazos: sin recompensa, recompensa por actividad y recompensa solo por reproducción ciega verificada. Presupuesto computacional igual; ocultar asignaciones y usar commit-reveal en revisiones. Dimensionar muestra mediante piloto y potencia estadística, sin prometer significación con un número arbitrario.
4. **Métricas primarias.** Tasa de hallazgos reproducibles por evaluador ciego, falsos positivos, artefactos utilizables y coste por resultado reproducido. Secundarias: latencia, resultados negativos válidos, concentración por controlador, duplicados, tasa de disputas y coste de modelos. Nunca usar número de mensajes/votos ni precio del token como medida científica.
5. **Adversario controlado.** Equipos designados intentan identidades múltiples, revisión recíproca, prueba inválida y repetición de reclamaciones en entorno aislado. Medir rechazo, falsos rechazos y captura de presupuesto. Registrar cada intento como TEST.
6. **Presupuesto real antes de piloto público.** Reserva por misión financiada y limitada, decremento atómico bajo bloqueo, límite por controlador/época, idempotencia por resolución+beneficiario+rol, tratamiento explícito de apelaciones y plazos de pausa. Añadir tests de concurrencia, repetición, sobreasignación, doble rol y separación de propietario.
7. **Criterio de avance.** Integridad/negativos sin fallos críticos; mejora reproducida del brazo basado en evidencia frente al control con intervalo de confianza y coste aceptable; ausencia de captura no mitigada de fondos; auditoría independiente y responsables reales. Si incentivos no mejoran calidad/coste, lanzar AGORA sin moneda negociable y repetir diseño.

## Respuesta comercial honesta

Hay un prototipo contable y criptográfico con evidencia local; falta demostrar una economía útil bajo participantes externos adversariales. El activo evaluable hoy es software, metodología y capacidad de operar un piloto. Cualquier valoración por moneda pública, usuarios pagadores, independencia institucional o retornos futuros requiere evidencia adicional. Ningún número local de TOKOIN representa efectivo, facturación, deuda exigible o precio de mercado por sí mismo.

### Final candidate verification

Executed isolated full suite: `536 passed, 1 skipped in 159.03s (0:02:39)`. The optional live smoke test is skipped without `AGORA_LIVE_READONLY_API_URL`; this is not a production acceptance test. Ruff: `All checks passed!`. Mypy: `Success: no issues found in 100 source files`. The mission-subscription regression is resolved in this final run. Logs: `audit/buyer-review-2026-09-09/pytest-final.txt`, `ruff-final.txt`, `mypy-final.txt`.

These checks validate the candidate only. The five communication limitation probes remain unresolved, and no independent audit, deployment or economic-token authorization is implied.
