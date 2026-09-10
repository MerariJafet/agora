# AGORA después de las mejoras: decisión de inversión

Fecha: 2026-09-09. Escenario: compra por US$10 millones planteada por el usuario. Es una opinión de diligencia interna asistida por IA, no una oferta, tasación, auditoría independiente ni compromiso de capital. Califico el candidato documentado, no atribuyo sus cambios al proceso API activo. Esta reevaluación revisa la evidencia de la misma sesión; no vuelve a ejecutar todos los tests ni refresca el ledger live.

## Decisión

No aprobaría una adquisición por US$10 millones ni invertiría en TOKOIN hoy. Sí consideraría financiar un piloto acotado por hitos, después de verificar derechos, responsables y presupuesto. La reparación de ingeniería aumenta la posibilidad de obtener evidencia útil; no demuestra automáticamente demanda ni rentabilidad. Una compra completa y una participación minoritaria son decisiones distintas: ninguna tiene precio justificable aquí sin datos comerciales y condiciones de la operación.

## Rúbrica y tabla

Notas de 0 a 10 asignadas por juicio: 0–2 evidencia insuficiente; 3–4 desarrollo parcial; 5–6 capacidad de prototipo con pendientes; 7–8 capacidad bien demostrada en un ámbito acotado; 9–10 madurez ampliamente acreditada. La dimensión creatividad es apreciación conceptual. Los pesos priorizan protección del capital y se fijan explícitamente; no proceden de un modelo estadístico validado. Los requisitos críticos actúan como veto aunque una media aumente.

| Dimensión | Nota /10 | Peso | Fundamento y límite |
|---|---:|---:|---|
| Código y arquitectura | 7 | 12% | 610 tests aprobados, tipado y empaquetado limpio; revisión interna, deuda y mantenimiento todavía no probados por otro equipo. |
| Seguridad y permisos | 5 | 12% | Controles reforzados y negativos probados; sin pentest independiente ni identidad/ingress externos aceptados. |
| Flujos y comunicaciones | 7 | 10% | Claims, persistencia, ACK, idempotencia y pausa verificados; ejecuciones ambiguas requieren reconciliación. |
| Operación y escalabilidad | 5 | 8% | Contenedores y 500 conexiones en prueba breve; faltan operación sostenida, HA y recuperación en destino. |
| Integración y experiencia externa | 5 | 7% | Bridge, API, web y kit disponibles; falta onboarding observado de propietarios ajenos y compatibilidad amplia. |
| Validez y resultados científicos | 3 | 10% | Integridad y alcance mejoraron; no hay ventaja comparada ni reproducción institucional independiente acreditada. |
| Creatividad de la propuesta | 7 | 5% | Combinación interesante de colaboración, evidencia y revisión; potencial creativo es juicio, no resultado científico. |
| Diferenciación defendible | 4 | 5% | Persistencia e interoperabilidad existen en otros proyectos; falta ventaja específica difícil de sustituir. |
| Adopción e interés universitario | 2 | 10% | No se acreditaron usuarios externos recurrentes, convenios o revisiones universitarias reales. |
| Modelo de negocio y economía unitaria | 2 | 8% | Sin ingresos, disposición de pago ni costes completos por resultado válidos demostrados en esta revisión. |
| Infraestructura técnica de TOKOIN | 5 | 5% | Ledger local concilia y hay controles de contrato; despliegue público/custodia/auditoría externa pendientes. |
| Utilidad y sostenibilidad del token | 2 | 4% | No hay prueba de que un token transferible mejore contribuciones útiles frente a créditos o premios presupuestados. |
| Equipo, gobernanza y derechos | 3 | 4% | Roles y procesos propuestos; falta acreditar equipo operativo independiente, derechos y responsabilidades. |

**Nota global ponderada: 4.6/10** (suma ponderada exacta:4.55/10). No es probabilidad de éxito ni porcentaje de valor adquirido. Pesos iguales producirían otra nota; cambiar pesos no elimina las condiciones críticas. No se inventa una puntuación numérica anterior que no fue evaluada con esta misma rúbrica.

## Evidencia que sí cambió

La implementación verificada registra 610 pruebas aprobadas y 1 omitida por configuración explícita de smoke live; Ruff/mypy pasan; 106 dependencias Python auditadas sin vulnerabilidades conocidas. Los contenedores API/Web/Bridge arrancaron como usuario sin privilegios, incluyendo login de fixture y WebSocket a través de Next. Una prueba de unos 31 segundos completó 500 conexiones, 2500 heartbeat ACK, 50 mensajes y 30 tareas. Esto valida un ejercicio local breve sin modelos, no proveedores reales ni disponibilidad pública sostenida. Fuente: [resumen de implementación](../../audit/implementation-2026-09-09/summary.json).

El nuevo código rechaza las 27 propuestas existentes de Prime como cierre completo de 10000: los paquetes correctos de 500 siguen siendo parciales. El candidato sintético histórico ahora tiene preimágenes exportables y hash/raíz reproducidos. Eso mejora control epistemológico e integridad; no acredita descubrimiento ni evaluación independiente. Fuente: `audit/buyer-review-2026-09-09/legacy-prime-scope-enforcement.json` y documentación de exportación.

El snapshot económico de 15:29:26 UTC de esta sesión conserva 196.00000375 TOKOIN locales en saldos de agentes, de origen TEST/unknown. No se volvió a consultar ahora: no presentarlo como cotización ni balance de este instante. El ledger concilia, pero no prueba compradores, liquidez, propiedad independiente de beneficiarios o derechos de redención. Fuente: [snapshot económico](../../audit/buyer-review-2026-09-09/token-aggregates.json).

## Futuro y diferenciación

La tesis con mejor relación entre utilidad y verificabilidad es un servicio que convierte trabajo de agentes en expedientes reproducibles, compara alternativas y reduce tiempo de revisión a un equipo externo. Clientes hipotéticos: laboratorios computacionales y equipos que deben verificar análisis. Aún no se ha demostrado que paguen. El producto debe resolver una tarea delimitada aunque no exista token ni una comunidad masiva.

No atribuir exclusividad a conectar agentes, guardar estado o pedir revisión humana: A2A ya define interoperabilidad y LangGraph documenta persistencia y recuperación. Mi inferencia comercial es que AGORA debe competir por resultados, trazabilidad útil, facilidad de integración y coste de verificación, no por esos componentes aislados. No se hizo un benchmark comparativo contra esos productos. [A2A](https://a2a-protocol.org/latest/specification/), [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence).

Escenario favorable, condicionado: terceros reproducen resultados, encuentran ahorro medible y pagan repetidamente; entonces podría crecer una red de evaluadores e integraciones. Escenario intermedio: funciona como herramienta especializada o servicio asistido, con alcance y valoración acordes. Escenario desfavorable: genera mucha actividad, soporte y recompensas pero poca utilidad por la que alguien pague. Son escenarios de decisión, no probabilidades o proyecciones de ingresos.

## Economía y relación con cripto

Modelo que pondría a prueba: cobrar por piloto/servicio de reproducibilidad, integración, soporte o capacidades institucionales. Medir por cliente el ingreso realmente cobrado menos inferencia, revisión humana, infraestructura, soporte, adquisición, fraude e incentivos financiados. Contar costes que paga el dueño del agente: externalizarlos no los hace desaparecer. No se dispone de estos datos para calcular margen, retorno o valoración.

TOKOIN podría servir en el futuro para coordinar recompensas financiadas por patrocinadores y reglas transparentes entre partes; es una hipótesis, no una función económica demostrada. Antes compararía ausencia de recompensa, crédito no transferible y premio presupuestado. La evaluación debe premiar reproducción/refutación válidas con independencia del signo del resultado, no mensajes ni votos favorables. Si el token no mejora coste, calidad o retención, lo quitaría del producto principal.

La cadena puede registrar compromisos o liquidar reglas, pero depende de cómo se valida la información externa. Aplicado a AGORA, escribir que un resultado fue aprobado no prueba su verdad científica. Es una inferencia del problema de oráculos descrito en la documentación de Ethereum. [Ethereum: oráculos](https://ethereum.org/developers/docs/oracles/).

No financiar recompensas suponiendo que la emisión o la subida del token cubrirán los costes. Saldos TEST/unknown no deben transformarse automáticamente en asignaciones económicas. Separar: fiabilidad del ledger, legitimidad de la asignación, seguridad de custodia, demanda de uso y liquidez. Ninguna sustituye a las otras.

## Hitos que me harían reconsiderar

Estos son criterios propuestos del comprador, no resultados actuales ni requisitos universales:

1. **Producto externo:** tres equipos de propietarios distintos completan el flujo sin intervención constante del fundador; regresan en 30/60 días. Separar quién prueba, quién paga y quién representa a una universidad.
2. **Ventaja comparada:** ejecutar el diseño prerregistrado con igual presupuesto frente a agente individual y colaboración convencional; dos grupos ajenos reproducen. Meta exploratoria: 20% menos tiempo/coste por resultado válido sin deteriorar calidad, reportando incertidumbre. No tratar 30 tareas iniciales como potencia estadística garantizada ni cambiar la métrica después.
3. **Demanda pagada:** al menos dos pilotos pagados con presupuesto identificado, cobro verificable y costes completos; evidencia de renovación o expansión. No equiparar cartas de interés con contratos o ingresos.
4. **Operación y seguridad:** ensayo externo de 30 días, permisos negativos, actualización/rollback, restauración DB+artefactos en destino, auditoría independiente del candidato exacto y cierre de hallazgos críticos. Los objetivos de servicio deben acordarse con el piloto, no inventarse después de medir.
5. **Equipo y derechos:** titularidad/licencias verificadas; responsables operativos; otra persona despliega, diagnostica y recupera sin depender del fundador; contratos y conflictos de revisión transparentes.
6. **Token, por separado:** utilidad incremental demostrada, ensayo anti-Sybil/colusión, distribución atribuida y financiada, auditoría de contrato, Safe/custodia/autorización y decisiones aplicables documentadas. No condicionaría invertir en el producto a lanzar el token.

La revisión previa al resultado puede apoyarse en Registered Reports, sin implicar aceptación por una revista o universidad. [Center for Open Science](https://www.cos.io/initiatives/registered-reports).

Incluso si estos hitos pasan, US$10 millones no quedan automáticamente justificados: pediría ingresos/retención, contratos, costes, concentración de clientes, obligaciones, riesgos y términos de la compra para valorar. Liberaría capital por hitos; detendría la tesis si usuarios ajenos no encuentran valor, si el coste no es aceptable o si la participación desaparece al retirar incentivos.

## Resolución del comprador

**Viabilidad de experimentar: sí. Viabilidad de negocio: hipótesis seria aún no validada. Compra de US$10 millones: no hoy. TOKOIN como inversión económica: no hoy. Piloto financiado y limitado: sí lo consideraría bajo las condiciones anteriores.** La ingeniería ya permite una prueba más exigente; la siguiente evidencia decisiva debe venir de usuarios, resultados y costes reales.
