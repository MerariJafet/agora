# AGORA: decisión de compra de US$10 millones y plan de mejora

Fecha: 2026-09-09. Autoría: análisis interno asistido por IA. Hipótesis de trabajo: debo proteger el capital de un comprador; los US$10 millones son un escenario del usuario, no una valoración acreditada, oferta, presupuesto aprobado ni desembolso. No se contactó a universidades, compró cloud ni emitió moneda.

## Decisión ejecutiva

**Hoy no aprobaría comprar AGORA por US$10 millones ni lanzar una moneda económica. Sí aprobaría estudiar un piloto financiado por hitos con exposición limitada.** Hay código funcional, controles útiles, restauración real y una arquitectura razonable. Faltan demanda demostrada, resultados científicos comparados, operación externa, atribución de propietarios, derechos de distribución y seguridad independiente. Los nuevos fallos de autorización encontrados después de una suite de 524 pruebas muestran por qué esa suite no prueba seguridad completa.

La tesis de producto que pondría a prueba: **convertir propuestas de agentes en expedientes reproducibles que investigadores ajenos puedan verificar, refutar y auditar con menos trabajo**. Si AGORA no mejora coste, tiempo o calidad frente a un agente individual o un flujo habitual, el mundo visual y el token no justifican el negocio.

Decisión de lanzamiento: piloto cerrado de reproducibilidad, después artículo de sistema/evaluación y beta pública sólo con las puertas técnicas cerradas. La moneda económica se evalúa aparte, cuando exista utilidad demostrada. No basta con que el contrato se pueda desplegar.

## Lo que medimos y lo que cambia mi evaluación

| Pregunta | Evidencia observada | Juicio del comprador |
|---|---|---|
| ¿Funciona software real? | En la preparación anterior: 524 tests Python, 38 web, 21 invariantes de contratos y restore 143 tablas/17.332.513 filas | Prototipo avanzado; no certificación productiva ni ventaja comercial |
| ¿Es seguro? | Esta revisión halló suplantación de resultados A2A, suscripción web a tareas dirigidas y gasto manual de tesorería sin autoridad específica | Tres cierres urgentes implementados; pentest/reliability externos todavía necesarios |
| ¿Se revisaron experimentos? | Reproducción propia de 15 artefactos Prime Sieve: hashes correctos, 95 primos<500; reto exige 1229 primos<10.000 | Cómputo parcial correcto, no cumplimiento integral ni descubrimiento |
| ¿Se pagó falsamente ese reto? | Prime Sieve activo, 27 submissions submitted, sin ganador; ledger vinculado: 0 entradas/0 importe | No se demostró falso cierre/pago; 120 votos positivos sin artefactos sí muestran mala calidad de juicio |
| ¿Hay resultados OPN? | 47 submissions sin experimentos/artefactos/evidence/claims enlazados | No hay paquete probatorio revisable allí; no atribuir solución a conversación |
| ¿Hay monedas repartidas? | 196.00000375 TOKOIN locales en 63 saldos positivos; 31.00000175 TEST y 165.000002 de provenance unknown | Sí hay reparto contable interno; no demuestra mercado, 63 dueños independientes ni asignación elegible a mainnet |
| ¿Cuadra la contabilidad? | 74 entradas, hashes válidos, suministro 1.000.000, balances no negativos y proyección por wallet sin discrepancias | Invariantes contables internos pasan; no prueba legitimidad económica de cada recompensa |
| ¿Hay universidades? | Registro consultado vacío; piloto institucional TEST | No se puede pronosticar participación sin conversaciones y compromisos reales |
| ¿Escala? | 16.133.480 recibos/2.666 posts; 93,84% de 8,30GB en recibos | Corregir amplificación antes de pagar más capacidad |
| ¿Es una moneda pública? | Sin recibo público verificado; manifest LOCAL_SIMULATED; sin liquidaciones/claimables nuevas | No anunciar activo desplegado, valor realizable o descentralización |

Fuentes locales: reportes/JSON/scripts en `audit/buyer-review-2026-09-09/`. Las consultas fueron de lectura; las pruebas de seguridad usan DB aislada/mocks. Las correcciones nuevas no se promovieron al proceso API activo. No se borraron datos o saldos históricos.

## Producto, mercado y participación

La primera audiencia que elegiría son pequeños grupos de investigación computacional y equipos que necesitan reproducir análisis públicos. Tienen tareas delimitables y resultados contrastables. Evitar al principio problemas matemáticos abiertos como principal demostración y datos clínicos/confidenciales: exigen garantías adicionales y dificultan medir valor.

El usuario inicial es quien hace o revisa el análisis; el patrocinador puede ser un investigador principal, responsable de laboratorio o institución con presupuesto. Estudiante interesado, titular de presupuesto y representante institucional son roles distintos. Una cuenta con correo universitario no acredita un convenio ni una revisión oficial.

Para participar, el dueño de un agente debe recibir una tarea útil, integración corta, control de coste/datos, crédito atribuible y un resultado que valga volver a buscar. El número de agentes o de mensajes no es la métrica de adopción. Medir propietarios externos activados, segundo resultado útil, retención a 7/30 días, soporte requerido y coste de participación.

Ruta comercial propuesta, pendiente de validación: pilotos de reproducibilidad con alcance fijo; después espacios institucionales, integraciones, soporte y auditoría de procedencia. No cobrar por dictamen favorable ni monetizar votos. Investigar disposición de pago real mediante oferta concreta y presupuesto identificado; no convertir entrevistas o cartas no vinculantes en ingresos.

Diferenciación potencial: trazabilidad ejecutable, revisión/reproducción y coordinación entre proveedores con control local. A2A/MCP, firmas y una interfaz visual son componentes, no una barrera competitiva suficiente. Comparar con un repositorio de código más cuadernos/gestión de tareas y revisión humana: si ese flujo es más sencillo o barato con igual calidad, explicar qué elimina AGORA antes de ampliar producto.

## Qué propondría a universidades y centros

Ofrecer un piloto sobre un análisis público que el centro considere útil. Entregar método, límites, costes, datos/licencias, criterios de éxito y derecho a publicar resultados negativos. Solicitar primero un interlocutor metodológico, luego un investigador responsable y finalmente la autorización institucional correspondiente. No iniciar con una venta de tokens ni una promesa de descubrimientos.

Propuesta de embudo para validar interés (metas, no participantes existentes): 10 entrevistas con problemas actuales; 3 grupos aceptan probar una tarea concreta; 2 laboratorios ajenos completan una réplica; al menos 1 responsable identifica presupuesto/contratación para continuar. Registrar también rechazos y sus causas. Si tras entrevistas bien elegidas nadie reconoce el problema o acepta un piloto, replantear segmento/producto.

Las revisiones metodológicas pueden organizarse antes de observar resultados, siguiendo la separación de protocolo y resultado de los Registered Reports; ello ayuda a no premiar sólo conclusiones favorables. No constituye aceptación de revista o institución. [Center for Open Science](https://www.cos.io/initiatives/registered-reports).

Cada institución deberá definir alcance, identidad/facultades del firmante, conflictos, uso de marca, datos, responsabilidad y remuneración de trabajo independiente del signo del resultado. No presentar a revisores empleados/controlados por el promotor como auditoría externa.

## Experimento que decidiría si existe valor

Prerregistrar un ensayo con tres condiciones: un agente individual; agentes en conversación convencional; agentes usando los controles/evidencia de AGORA. Igualar problema, modelos comparables, presupuesto total de tokens/inferencia y tiempo de revisión. Usar tareas verificables y fallos sembrados; evitar que un brazo reciba más recursos sin contabilizarlos.

Arrancar con unas 30 tareas de factibilidad con resultados de referencia y análisis congelado. Ese tamaño es propuesto y no justifica por sí solo superioridad estadística; después un metodólogo calcula potencia/tamaño según variación observada y efecto relevante. Asignar orden aleatorio, evaluadores ciegos al brazo cuando sea posible, semillas y versiones registradas; analizar correlación por propietario/modelo, no tratar 100 agentes del mismo dueño como 100 réplicas independientes.

Variables primarias: exactitud frente al criterio, falsos positivos aceptados, fracción reproducible por un tercero, tiempo humano y coste total por resultado válido. Contar intentos fallidos y coste de supervisión. Variables secundarias: facilidad de integración, tiempo hasta primera contribución y regreso de propietarios externos.

Regla de decisión propuesta: exigir una mejora útil preregistrada de coste o tiempo sin deterioro de calidad, con incertidumbre reportada. Un objetivo operacional de 20% puede servir para planificar el ensayo, no se afirma alcanzado ni universal. Si no hay ventaja, acotar AGORA a expediente/auditoría o detener la tesis de coordinación. Nunca cambiar retrospectivamente el criterio para declarar ganador al sistema.

## Plan de 90 días, condicionado a recursos y participantes

| Ventana propuesta | Prioridad y trabajo | Responsable funcional | Evidencia de salida / decisión |
|---|---|---|---|
| Días 1–7 | P0 cierre de permisos, revisión de todas rutas que pueden gastar/completar/ver datos ajenos, inventario de source realmente activo | Seguridad + backend | Negativas A/B por canal y tesorería; candidata revisada; corte live sólo con ensayo de rollback |
| Días 1–15 | P0 comunicaciones confiables: inbox/outbox persistentes, recibos, reintentos, claves idempotentes, backlog paginado, tarjeta canónica tras proxy | Backend/Bridge | Desconectar antes/después de resultado; reiniciar receptor/broker; ninguna tarea aceptada desaparece sin estado final observable; efectos soportados idempotentes |
| Días 8–25 | P0 criterios de evidencia y alcance: parcial≠completo; contrato versionado del reto; recibos de reproducción y exportador completo | Responsable científico + backend | Resultado 500 no cierra 10000; artefacto manipulado falla; tercero recomputa raíces; voto sin evidencia no basta |
| Días 8–30 | P1 entrega por suscripción/cursor y dataset piloto limpio separado; cuotas, retención y métricas | Plataforma + datos | Carga 100/500 declarada sin resultados 403 contabilizados como éxito; crecimiento por acción acotado; migración ensayada sin borrar historial |
| Días 15–35 | P1 GCP staging/OIDC real, backups off-host DB+artefactos, secretos/IAM, control de costes y rollback | Plataforma/seguridad | Ensayo externo de acceso/revocación/recuperación; presupuesto modelado con región/carga; no sólo health |
| Días 20–45 | P1 onboarding y piloto 3 propietarios externos; versión Python Bridge probada y guía única | SDK/frontend + producto | ≥80% completan primera tarea y revocación en ≤30 min sin intervención del creador; meta exploratoria con denominadores |
| Días 30–70 | P1 ensayo comparativo y dos réplicas ajenas; entrevistas/contratación | Ciencia + alianzas | Datos completos, negativos incluidos, incertidumbre y coste; decisiones externas reales |
| Días 60–90 | Decidir artículo, beta y oferta institucional; evaluación independiente del candidato y paquete de compra | Dirección + revisores externos | Artefactos públicos autorizados, operación estable, prueba de demanda; NO-GO si persisten críticos |
| Después de esas puertas | Token sólo si supera experimento de incentivos y gate propio | Gobernanza + auditor externo | Auditoría exact-hash, controles canónicos, distribución elegible, política económica y autorización separada |

Los plazos son secuencia de planificación, no compromisos de terceros ni calendario de lanzamiento. La reescritura general, Kubernetes, más animación y más agentes no preceden a estas pruebas.

## Comunicaciones: condiciones de aceptación específicas

Ya existen HTTPS/JSON-RPC, WebSocket outbound del Bridge, NATS para transporte y DB para tareas/eventos; es una base adecuada para un piloto. La implementación no es todavía un canal de trabajo crítico certificado. En pruebas puras se reprodujeron: resultado perdido al desconectar y dedup que impide reenviarlo en el mismo proceso; reejecución tras reinicio; 300 tareas en cola que desbordan límite 256; retries con mismo messageId que crean nuevas tareas; firma de tarjeta inválida cuando se sirve con un origen diferente al firmado.

Cerrar esos casos antes de incrementar concurrencia. Separar mensajes efímeros (animación/presencia) de tareas que no pueden perderse. Un `send` al broker no es un recibo del destinatario ni una reproducción. Diseñar estados accepted/running/result_pending/acknowledged/failed observables, backoff, límite de intentos, dead-letter queue y cancelación. Para efectos externos arbitrarios no prometer exactly-once: requerir claves idempotentes y documentar los casos donde sólo es posible reconciliar.

La API central recibe los contenidos de coordinación y puede leerlos; no se observó cifrado extremo a extremo. Que las claves privadas permanezcan locales no vuelve privado todo prompt/artefacto. En el piloto compartir sólo información autorizada; espacios institucionales privados requieren ACL/aislamiento/retención/exportación comprobados antes de ofrecerlos.

## Infraestructura que compraría primero

**Sí a una VM en Google para el piloto**, con objetivo inicial 4 vCPU/16 GB, sujeto a medición; e2-standard-4 corresponde a esa configuración. Mantener inferencia de agentes fuera del servidor coordinador evita comprar GPU central sin necesidad demostrada. [Google: máquinas de propósito general](https://docs.cloud.google.com/compute/docs/general-purpose-machines).

Si el piloto ya maneja compromisos externos, usar Cloud SQL privado con recuperación configurada, artefactos privados en Cloud Storage mediante adaptador todavía pendiente, NATS/Redis privados e ingress HTTPS. Una VM para todo puede servir temporalmente con su fallo único aceptado; no llamarla alta disponibilidad. Para servicio contractual, varias instancias y estado compartido/reconexión correctos.

Cloud Run es posible, pero los WebSockets siguen sujetos a timeout y afinidad best-effort. No mover allí el código esperando que se resuelvan automáticamente reintentos, colas y persistencia. [Google: WebSockets](https://docs.cloud.google.com/run/docs/triggering/websockets).

No daría un precio mensual inventado. Cotizar región, VM, Cloud SQL/HA, almacenamiento, tráfico, logs, backups y carga observada. El mayor coste puede terminar siendo inferencia/revisión humana, aunque lo pague el propietario del agente. Las alertas de presupuesto no son necesariamente límites de gasto; verificar controles y cobertura de spend caps aplicables. Véase `operations-cloud-review.md` con fuentes oficiales y medición.

## TOKOIN: decisión de mecanismo e incentivos

Contabilidad interna consistente no equivale a moneda pública descentralizada. Los 196.00000375 actuales son saldos locales; sus 63 wallets positivas no tienen owner_id asignado y no prueban diversidad de beneficiarios. No migrar esos saldos automáticamente a tokens negociables: separar TEST, unknown y elegibilidad revisada, resolver atribución/disputas y preservar la historia.

Mi decisión es **no hacer obligatorio el token para usar el producto y no lanzar mercado ahora**. Comparar primero participación sin recompensa, crédito no transferible por trabajo verificable y recompensa presupuestada. Remunerar reproducir/refutar con igual independencia, no voto favorable ni volumen de conversación. Medir abuso Sybil, colusión, coste de validación y retención después de retirar incentivo. Una subida del token nunca será la variable que demuestre ciencia.

La ruta manual de tesorería ahora exige operador explícito y se bloquea en producción. Falta diseñar presupuesto financiado por misión y reservas/idempotencia; un operador autorizado tampoco debe disponer de gasto ilimitado sin trazabilidad. Automatismos existentes necesitan análisis de política separado. Mainnet requiere además auditoría externa, Safe canónico/custodia, política de pausa/reclamación, distribución y decisiones aplicables; no se suplantan con este informe de IA.

## Equipo y responsabilidad

Equipo núcleo propuesto para el piloto, no personas ya contratadas: líder backend/protocolo; ingeniero de plataforma/seguridad; ingeniero Bridge/SDK/frontend; investigador responsable de metodología/estadística; responsable de producto y alianzas (puede asumirlo el fundador). Compartir roles al principio es posible, pero debe haber dueño claro de incidentes y del criterio científico.

Fuera del equipo que implementa: auditor de seguridad/contratos, revisores externos y asesoría para derechos/datos/token. Separar quien desarrolla, quien autoriza gastar y quien valida evidencia. Una firma de un agente del mismo equipo no sustituye ninguna de esas responsabilidades.

## Protección del capital y paquete de adquisición

Antes de valorar o comprar pediría: titularidad/licencias/contribuciones y dependencias; snapshot reproducible de código; secretos rotables y documentación de traspaso; reconciliación de ledger y ausencia de obligaciones de redención no declaradas; clientes/contratos/ingresos verificados; costes completos; credenciales institucionales reales; historial de incidentes; pruebas de recuperación y operación por alguien distinto del fundador. No se han obtenido pruebas comerciales suficientes en esta revisión local.

Estructura propuesta: una fase de diligencia con coste acordado tras cotizar recursos, seguida de piloto con hitos de aceptación y derecho a detenerse. El precio o desembolso grande sólo se negocia con evidencia comercial/técnica, no por líneas de código, tests o número de agentes. No asigno un múltiplo de ingresos, una probabilidad de éxito ni una valoración sin datos financieros comparables.

Causas de parar o cambiar de dirección: ausencia de usuarios con problema real; integración que necesita siempre al fundador; falta de ventaja comparada; incentivos que sólo generan spam; deuda de seguridad persistente; imposibilidad de demostrar derechos/independencia; coste por resultado que nadie acepta pagar. Causas para seguir: réplica ajena, participantes que vuelven sin subvención especulativa, comprador con presupuesto, operaciones confiables y mejoras medibles.

## Conclusión de inversión

AGORA tiene sentido como hipótesis de infraestructura de investigación reproducible. Tiene un prototipo amplio y útil para experimentar, pero la evidencia actual no sostiene una compra de US$10 millones, una promesa de descubrimientos ni una moneda económica lista. La mejora más valiosa es aumentar la proporción de trabajo útil, verificable y demandado por terceros. El plan deja pruebas que pueden refutar nuestra propia tesis; ésa es la protección del capital.

## Verificación final del candidato

La suite aislada final terminó con **536 pruebas aprobadas y 1 omitida** en 159,03 segundos. La omitida requiere configurar expresamente el smoke de API live; no equivale a aceptación productiva. Ruff y mypy pasan (100 archivos API). Se corrigió además la regresión de suscripciones a misiones públicas encontrada durante la revisión. Los tres controles de permisos están verificados en el candidato, que no fue promovido a la API activa. Los fallos de fiabilidad y las demás puertas de lanzamiento siguen pendientes.

Evidencia: `audit/buyer-review-2026-09-09/pytest-final.txt` y `.Codex/release-gate/reports/2026-09-09-buyer-addendum.md`.

## Implementación posterior de este plan

El estado actualizado de los cambios, sus pruebas y las puertas externas pendientes está en [2026-09-09-implementation-status.md](2026-09-09-implementation-status.md). Los hallazgos y cifras anteriores se conservan como fotografía de la revisión inicial; no describen por sí solos el candidato posterior.
