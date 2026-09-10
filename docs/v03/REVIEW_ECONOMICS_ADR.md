# ADR V0.3: ReviewReceipt y dos fases del presupuesto científico TEST

Decisión experimental: conservar exactamente el presupuesto nominal de un TOKOIN por reto y el reparto 10/10/51/20/9. Separar el asentamiento del 20% de revisión del asentamiento del 80% restante. No reservar ni crear moneda al abrir un reto.

Dos revisores registrados, distintos del autor y de los contribuyentes, deben comprometer y revelar recibos firmados ligados al mismo árbol de contribución. El recibo incluye valoración metodológica, evidencia, replicación, conflicto declarado y referencias verificables. La elegibilidad estructural de trabajo NO depende del sentido del dictamen: APPROVE, REJECT, INCONCLUSIVE y REQUEST_REPLICATION reciben la misma regla de reparto del pool de revisión.

Tras resolución científica y de objeciones, science_settle_review puede crear como máximo 0.20 TOKOIN por reto, divididos de manera determinista entre los recibos admisibles. Requiere dos recibos válidos; una sola clave no puede emitir. Permanecen bloqueados 365 días por el mismo protocolo. La creación acumulada y el cap TEST de 500 siguen aplicándose. Duplicar recibo, compensación o reto ya asentado falla.

Sólo una conclusión soportada aprobada por ambos revisores permite science_settle_result: emite los 0.80 restantes para proposer/solver/contributors/infra, respetando sus porcentajes del presupuesto nominal. El solver debe referenciar un nodo de resultado elegible; no se infiere del último mensaje. Rechazo, inconclusión o solicitud de replicación no crean ganador ni emiten ese 80%; permanece UNISSUED, sin reasignarlo a otros pools.

La separación es una nueva versión de protocolo científico activada explícitamente en génesis TEST. V0.2 y sus saldos/historia permanecen reproducibles, sin migración silenciosa. Los tipos legacy de autorización no pueden saltarse la máquina científica en un génesis V0.3. No se introduce una wallet tesorera, clave de mint administrativa, premine ni alteración de máximo.

Limitación económica explícita: en investigaciones fallidas no se emite un reparto completo del presupuesto nominal; sólo se devenga la parte correspondiente a trabajo de revisión. Así se elimina la dependencia directa del pago del reviewer respecto de aprobar, sin fingir que las demás partes ganaron. Esto no prueba que desaparezca todo incentivo indirecto o colusión.

Límites de calidad: validación determinista comprueba firmas, identidades, vínculos, estado y recibos, no la verdad de una valoración. La campaña LLM evalúa por separado rigor de revisión y exactitud científica. Grupos TEST son identidades declaradas y no instituciones humanas independientes. Compensación real, financiación sostenible y adopción siguen fuera de esta iteración.

## Segunda iteración: correcciones adversariales

Los fallos iniciales quedan conservados en `audit/v03/security`. El protocolo ahora compara tanto el controlador declarado de la identidad como el controlador del registro de revisores del génesis contra los autores. Además, el génesis cerrado compromete el hash exacto de cada identidad y su clave monetaria; otra clave no puede adelantarse a registrar ese pasaporte ni cambiarlo silenciosamente. Este registro TEST es preparado por el operador y verificable contra los pasaportes publicados; no demuestra identidad institucional externa ni custodia privada de fondos por un modelo.

RESULT_80 mantiene una dependencia explícita de REVIEW_20. La impugnación admitida de la revisión detiene la maduración dependiente. Al desestimarse, se conserva el tiempo pausado; una revisión material o invalidación revoca la recompensa de resultado aún no finalizada y conserva la creación histórica dentro del cap. Una invalidación científica posterior a madurez impide nuevos resultados dependientes, sin confiscar balances ya finalizados. Si coinciden impugnaciones directas y de dependencia se añade conservadoramente la demora: puede prolongarse el bloqueo, jamás acortarse. Eliminar esa sobreextensión requiere especificar y probar una unión de intervalos, no cambiar el reloj informalmente.

Los tipos de eventos tienen predecesores verificables en sus ancestros: reto → hipótesis → contribución → evidencia → experimento → resultado → replicación. Un recibo no puede convertir una etiqueta de replicación anterior al experimento en un ciclo válido. Esta restricción comprueba orden y vínculos; una ejecución ausente por parámetros incompletos debe declararse como tal en los artefactos y evaluarse como inconclusa.

La distribución de contribuyentes en esta iteración utiliza elegibilidad binaria y un peso por autor único con contribución/resultado/replicación, sin acumular peso por mensajes repetidos. No demuestra valoración científica proporcional, resistencia Sybil de propietarios ni protección suficiente contra granjas de revisiones. El flujo sirve para estudiar esos problemas con TOKOIN TEST no reconocible; no autoriza emisión económica pública.
