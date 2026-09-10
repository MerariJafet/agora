# Protocolo de recompensa científica V2

AGORA conserva sus candidatos y genealogía. El puente prepara una autorización que no tiene por sí misma capacidad de emitir. El objeto fija `reward_id`, `research_id`, `candidate_version`, `protocol_version`, `genealogy_root`, los hashes del paper, datos y código, `reward_total`, los grupos ponderados, `distribution_root` y los controladores participantes declarados. Todos quedan vinculados por `authorization_hash` antes de la revisión ciega.

Dos instituciones registradas y con grupos de control declarados distintos publican primero sus compromisos. Sólo después de ambos compromisos pueden revelar sus dictámenes. La emisión exige dos veredictos compatibles: `APPROVED` o `APPROVED_WITH_MINOR_CHANGES`. Este último sólo puede referirse a cambios no materiales que no invaliden la versión revisada. `REJECTED`, `REQUIRES_REVISION` e `INSUFFICIENT_EVIDENCE` impiden autorizar la recompensa.

La aplicación comprueba el reparto, los destinos institucionales, la dirección de infraestructura fijada en génesis y los conflictos declarados. No permite más de una recompensa no revocada por investigación. El último mensaje no identifica automáticamente al autor de la solución; la asignación requiere justificación científica.

En TEST, cada autorización válida crea exactamente un TOKOIN bloqueado, dentro del límite acumulativo de 500. El monto no depende del número de mensajes, votos o agentes. Los pesos de contribución son compromisos revisados, no una prueba automática de valor. La financiación de revisiones adversas y de trabajos finalmente rechazados sigue abierta antes de usar el protocolo con valor económico.

El bloqueo incorpora tiempo de creación, hashes de revisión, estado y contador de maduración. La aplicación calcula la maduración a partir del tiempo consensuado; no acepta una fecha de desbloqueo arbitraria del emisor. Una denuncia presentada queda en la historia. Sólo una decisión de admisión con dos firmas institucionales cambia `LOCKED` a `CHALLENGED` y pausa el reloj. La protección frente a censura de esa admisión sigue pendiente.

El recorrido monetario implementado es `LOCKED → CHALLENGED → LOCKED` o `REVOKED_BEFORE_FINALITY`, y `LOCKED → FINALIZED` cuando se cumple la maduración. AGORA mantiene su propio ciclo de investigación y publicación; este prototipo no implementa automáticamente todos los estados del plan maestro ni migra la base activa. Una corrección posterior a la finalidad preserva la historia científica y no confisca fondos ya finalizados.
