# Ventana de impugnación científica de 365 días

La duración es fija: **31.536.000 segundos**, equivalentes a 365 días de 86.400 segundos. No son 365 bloques. El adaptador obtiene el tiempo del bloque confirmado por CometBFT y lo representa en segundos enteros. Dos bloques pueden compartir segundo después de esa conversión; el tiempo de la aplicación nunca retrocede. La máquina de estados aislada no autentica por sí sola el tiempo: esa garantía depende del motor y de su configuración verificada.

Al autorizar una recompensa, `elapsed` comienza en cero, `last_started` toma el tiempo del bloque y `unlock_at` persiste tiempo del bloque +31.536.000. Finalización compara ProtocolTime>=unlock_at; después de pausa se recalcula con tiempo restante. Mientras el estado sea `LOCKED`, la maduración acumulada es `elapsed + block_time - last_started`. Una decisión `ADMIT` con dos firmas institucionales válidas acumula el intervalo transcurrido y cambia el estado a `CHALLENGED`. Durante esa pausa no se consume tiempo de maduración.

Una denuncia `SUBMITTED` contiene el identificador del claim, compromisos de evidencia y método, y la identidad firmante. **Su mera presentación no pausa el reloj ni bloquea la finalización.** Permanece en la historia, pero solamente su admisión mediante dos firmas institucionales activa la pausa. Esta separación evita que cualquier clave sin fondos congele indefinidamente una recompensa publicando hashes arbitrarios.

La decisión no elimina el riesgo de censura: los revisores podrían demorar o suprimir la admisión de una impugnación válida hasta después del vencimiento. Antes de habilitar una economía real hacen falta disponibilidad verificable de evidencia, plazos de respuesta, un procedimiento de apelación y pruebas de resistencia a censura y spam. El prototipo no afirma haber resuelto ese problema. Un estado `SUBMITTED` tampoco debe mostrarse en la interfaz como prueba de que la impugnación carece de mérito.

Después de una impugnación admitida, `REJECT` o `MINOR` reanuda `LOCKED` con el tiempo acumulado intacto y `last_started` actualizado. `MATERIAL` o `INVALIDATE` revoca la recompensa provisional. Una nueva versión material necesita un candidato y revisiones nuevos, una autorización nueva y otros 365 días completos. La creación acumulada consumida por la recompensa revocada no vuelve a estar disponible.

Una recompensa finalizada no se confisca de forma retroactiva si aparece conocimiento posterior. La corrección modifica la genealogía científica mediante nuevas versiones; no autoriza a reescribir balances ni bloques históricos.

Las pruebas de días 364 y 365 y de correcciones usan tiempo simulado en pruebas unitarias de la máquina de estados. No demuestran que haya transcurrido un año real. La red TEST no acelera el reloj para presentar fondos como maduros, y ningún resultado TEST genera derechos de reconocimiento económico.

V0.2: una apelación automática con evidencia nueva y revisión firmada; no cambia reglas de admisión ni resuelve censura. Invalidación científica posterior se conserva mediante invalidate_finalized sin alterar saldos. ADR_ALPHA_V02_PROTOCOL.md detalla consecuencias.
