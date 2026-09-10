# Política monetaria nativa

TOKOIN conserva ocho decimales: **1 TOKOIN = 100.000.000 ACEROS**. El límite global es 100.000.000.000.000 unidades mínimas, equivalente a un millón de TOKOIN. Ninguna transacción puede modificarlo. El génesis comienza con emisión cero, sin tesorería preminada, emisión administrativa, confiscación ni edición de balances. Un software que altere esas reglas deja de ser conforme con este protocolo.

La invariante es `circulating + locked + revoked = total_created`. La creación acumulada nunca supera 500 TOKOIN en la red TEST ni el máximo global del protocolo. Las unidades revocadas siguen consumiendo ese presupuesto acumulado; no se recicla capacidad de emisión. No existen reservas adicionales en esta versión: `protocol_reserved_supply = 0`.

`UNISSUED` es la diferencia entre el máximo y la creación acumulada, no el saldo de una wallet. Finalizar mueve unidades bloqueadas a circulación sin aumentar la creación acumulada. El saldo finalizado no debe sumarse de nuevo a circulación como si representara otra clase de activos.

Las simulaciones comparan `fixed_1`, `evidence_bands_1_3_10` y `annual_budget_10000` bajo cuatro tasas supuestas de éxito y horizontes de 10, 25, 50 y 100 años. Son escenarios de emisión, no predicciones de precios, demanda o descubrimientos. No se introduce un algoritmo de reducción de recompensas. El monto fijo de un TOKOIN se selecciona únicamente para ensayos TEST y evita que los revisores elijan discrecionalmente cuánto emitir.

La política económica definitiva permanece abierta. El modelo de presupuesto anual supone que se conoce el número de éxitos de la época y requiere un mecanismo de cierre antes de ser implementable. Sus resultados de simulación no autorizan pagos reales.

`TOKOIN_NATIVE_REWARD_V2` aplica el reparto 10/10/51/20/9. Cada pool usa aritmética entera; el total debe sumar exactamente 100 %. Las distribuciones ponderadas utilizan mayor resto y dirección como desempate. Los protocolos históricos mantienen su reparto 1/10/60/20/9. Los pesos requieren respaldo en contribuciones y revisión científica fuera del consenso; por sí solos no miden verdad ni originalidad.
