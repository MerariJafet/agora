# Invariantes monetarias y alcance de las pruebas

El núcleo usa enteros estrictos. En TEST: `circulating + locked + revoked = created <= 500*10^8 <= 10^14`. `reserved=0`. Las asignaciones revocadas consumen capacidad histórica; no se reemiten por quemar.

Argumento de preservación por transición, no prueba formal mecanizada:

1. Génesis válido tiene todas las magnitudes en cero y rechaza parámetros monetarios distintos de las constantes.
2. `authorize` comprueba los límites antes de aumentar `created` y `locked` por la misma cantidad; impide reutilizar reward/candidato e investigación no revocada.
3. `finalize` disminuye locked e incrementa balances exactamente por las asignaciones cuya suma fue comprobada; created no cambia.
4. Revocación disminuye locked y aumenta revoked por el mismo monto; created no cambia.
5. Transferencia exige firma, nonce y saldo suficiente; resta y suma la misma cantidad. No usa saldo locked.
6. Revisión e impugnación no incrementan supply. Toda transición verifica conservación antes de devolver el nuevo estado. Un fallo descarta la copia completa.

Bajo estas reglas y un génesis válido, inducción sobre la secuencia de bloques conserva los límites. La conclusión depende de ejecutar código conforme, validar las firmas, aplicar el orden acordado y respetar la persistencia; no reemplaza una auditoría criptográfica o demostración formal de la implementación.

Pruebas automatizadas: MAX+1 mínima unidad, piloto 500+1 mínima unidad, dos autorizaciones cerca del límite, reparto con 1000 casos generados determinísticamente, replay y nuevo ID de reward, doble gasto, firma/cadena alterada, un solo revisor, dictámenes incompatibles, conflicto declarado, ingreso de float/bool, día 364, minor/material, finalización temprana, crash antes de commit, concurrencia de writers, corrupción, altura conflictiva y tiempo regresivo.

Las fixtures de borde construyen estados contables coherentes cerca del límite para probar la transición; no son 500 rewards científicos reales. El harness CometBFT emite 1 TOKOINTEST locked, rechaza su replay, finalización temprana y gasto, y verifica que la recuperación no duplica creación. El reloj científico acelerado sólo aparece en pruebas de máquina de estados.

Datos ejecutados: `audit/native-2026-09-09/unit-results.xml`, `network-test.json`, `independent-process-replay.json`, `monetary-simulations.json`. No se afirmó cumplimiento de 365 d reales, auditoría independiente ni reproducción en otra máquina.
