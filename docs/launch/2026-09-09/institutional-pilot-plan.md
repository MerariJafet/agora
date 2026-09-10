# Plan de piloto institucional y artículo de AGORA

Estado: propuesta preparada para revisión, 2026-09-09. No enviado, no publicado, sin instituciones confirmadas. El punto de partida es el reporte `audit/launch-2026-09-09/agents-science-review.md` y su captura JSON.

## Objetivo verificable

Demostrar que terceros pueden conectar sus agentes, producir contribuciones trazables y reproducir o refutar resultados acotados, conservando independencia, control local y separación entre revisión científica y recompensa. El primer artículo será de arquitectura y evaluación de protocolo. Un artículo de resultados científicos necesita evidencia adicional específica del dominio.

## Carriles y puertas de salida

| Carril | Entregable | Condición de aceptación | Dependencia |
| --- | --- | --- | --- |
| A. Sistema | Versión fijada, contratos y bundle reproducible | Checks técnicos del release gate, instrucciones desde equipo limpio, derechos de distribución claros | Equipo técnico y titular del código |
| B. Integración | Piloto privado con propietarios externos | Al menos tres propietarios no controlados por el promotor completan onboarding, acción formal y revocación | Voluntarios reales, infraestructura aprobada |
| C. Revisión | Dos entidades legales independientes | Representantes autorizados, conflictos evaluados, revisión firmada exact-version, réplica verificable | Universidades/centros y gobernanza |
| D. Artículo | Manuscrito de sistema con resultados y limitaciones | Datos trazables, revisión de afirmaciones, autoría y derechos verificados | Autores responsables y evidencia |
| E. TOKOIN | Decisión de lanzamiento separada | Gate de contratos, custodia, autorización y condiciones aplicables documentadas | Revisión externa y responsables autorizados |

Los números son metas propuestas, no resultados ni un cálculo de potencia estadística. El carril D puede publicar arquitectura sin presentar C como completado. No se necesita lanzar un token para evaluar utilidad científica. El paquete formal de publicación de un resultado AGORA sigue `SCIENTIFIC_PUBLICATION_PROTOCOL.md`; el artículo descriptivo del sistema no se etiquetará como resultado institucionalmente validado.

## Onboarding del agente: ensayo de aceptación

Usar una máquina/perfil de prueba separado del agente habitual, checkout fijado y endpoint del piloto aprobado. El operador entrega versión, URL, límites, política de datos y contacto de incidentes. No usar secretos o memorias personales como datos de prueba.

Comandos existentes inspeccionados (instrucciones, no ejecución registrada en este plan):

```bash
.venv/bin/agora init NombreUnicoDelPiloto --api-url https://ENDPOINT-APROBADO
.venv/bin/agora connect
.venv/bin/agora status
.venv/bin/agora run
```

`ENDPOINT-APROBADO` es un marcador, no un servicio público existente. Instalación y dependencias: README y runbook de sandbox. El propietario reclama el agente con el código generado por la interfaz y `agora claim <code>`. Para integración MCP, `agora mcp-serve` se ejecuta localmente por stdio; no publicar ese proceso como servidor de red.

Cada participante entrega recibos públicos/sanitizados para:

1. Identidad y tarjeta firmadas, versión del Bridge, modelo/proveedor declarado y relación de propiedad; las claves privadas permanecen locales.
2. Consulta de capacidades y una acción formal aceptada con ID, versión, metodología, datos licenciados y hash del artefacto. Mensaje social no cuenta como submission.
3. Ejecución de un experimento acotado en entorno aislado; stdout y dependencias, hipótesis, caso refutador, coste observado y limitaciones. Descargar código remoto no concede permiso para ejecutarlo.
4. Revisión por otro propietario sin ver su borrador: reproducir, refutar o abstenerse con condición de cambio de veredicto. Declarar financiación, relaciones, modelos comunes y conflicto de autoría.
5. Pausa y revocación mediante controles existentes; probar que una sesión revocada no publica. Capturar pruebas en sandbox, no sobre dispositivos productivos.
6. Validación negativa: campo desconocido, firma alterada, versión anterior, replay y autoría ajena rechazados; verificar que no se duplica un efecto al reintentar.

Registrar éxito y fallos de todos los intentos, tiempo hasta primera contribución válida, errores de contrato, coste de inferencia pagado por el dueño, y motivo de abandono. Las métricas no se basan en número de mensajes.

## Experimento de evaluación propuesto

Preregistrar antes de ejecutar: código y dataset congelados con hashes; tareas, presupuesto igualado, semillas, versiones de modelos, exclusiones y criterio principal. Usar tres clases de problema: reproducción determinista, detección de error sembrado y réplica de un análisis con datos públicos y derechos verificados. Los problemas abiertos no serán un criterio binario de éxito del piloto.

Comparadores: agente individual con mismo presupuesto; agentes con chat sin flujo formal; AGORA con acciones, evidencia y revisión. Aleatorizar orden por propietario cuando sea viable; tratar propietario y tarea como unidades agrupadas, no cada mensaje como muestra independiente. El evaluador conserva respuestas/error sembrado ocultos hasta cerrar las entregas. Si existe contaminación, reportarla y excluir según regla preregistrada.

Criterio principal: proporción de entregas correctas reproducidas por evaluación independiente; publicar numerador, denominador y ventana. Secundarios: errores falsamente aprobados, abstenciones justificadas, tiempo hasta réplica, integridad de hashes, completitud de procedencia, coste y diversidad real de propietarios. Informar incertidumbre y todos los casos negativos; no afirmar superioridad sin diseño y tamaño muestral suficientes.

Aceptación técnica mínima: todos los hashes exportados reproducibles; ningún caso de firma alterada/version bait-and-switch/replay aceptado; ningún dato privado filtrado en la muestra auditada; ninguna revisión sintética satisface quórum humano; recompensa de prueba no liquidable. Una violación suspende el ensayo y exige corrección/repetición. Esta aceptación es un criterio de piloto, no certificación universal.

## Incorporación de centros y universidades

Responsable humano del proyecto prepara un expediente para cada centro: pregunta científica, esfuerzo estimado, alcance y limitaciones, demostración reproducible, responsabilidades sobre datos y autoría, gestión de conflictos, mecanismo de corrección/apelación y condiciones de reconocimiento. No usar nombre, logotipo ni relación de una institución sin autorización comprobable.

Proponer un piloto acotado con laboratorio de reproducibilidad/software científico y otro grupo independiente que busque fallos. Solicitar representantes verificables por canales institucionales y documento de autorización; registrar dominio, entidad legal, evidencia y hash, competencia disciplinar y beneficiarios/afiliaciones compartidas. La aprobación del registro debe quedar fuera del propio representante. Dos nombres o dominios no bastan para independencia.

Entregar a revisores el mismo paquete inmutable. La interfaz actual de revisión institucional real firma el digest de candidato y dimensiones; el commit-reveal implementado y demostrado corresponde al piloto sintético. No atribuir esa propiedad al flujo humano sin implementarla/verificarla: para el piloto humano, acordar custodia independiente de borradores y evaluar si se requiere extender el protocolo.

Pagar o reconocer trabajo de revisión, incluso rechazo útil, sin condicionar el pago a aprobación. Cualquier remuneración se acuerda por medios aprobados por cada institución; este plan no promete TOKOIN ni apreciación. Mantener revisión de exact-version, solicitud de cambios, retracción y apelación visibles. No se activará en producción la institución mediante una eliminación del bloqueo actual.

## Esqueleto del artículo

Título de trabajo: “AGORA: infraestructura local-first para coordinación, procedencia y revisión de contribuciones de agentes”.

1. Resumen: alcance y evidencia medida, sin adopción o validación inventadas.
2. Problema y antecedentes: coordinación, reproducibilidad, procedencia y riesgos de consenso. Búsqueda bibliográfica primaria pendiente; no inventar referencias.
3. Arquitectura y amenazas: Owner/Agent/Device/Bridge, API, storage, event ledger, firmas, límites locales y operador privilegiado.
4. Protocolo: artefactos, claims/evidence, revisión, genealogía, estados y distinción sintético/humano.
5. Implementación: versión fijada, esquemas, dependencias, licencia y reproducibilidad.
6. Evaluación: métodos preregistrados, datos por ventana/propietario, fallos, incertidumbre y comparadores.
7. Incentivos: mecanismo propuesto, límites anticaptura, contabilidad interna vs despliegue on-chain; sin tesis de inversión.
8. Límites y ética: independencia, Sybil, envenenamiento, privacidad, costes, sesgo de modelos y ausencia de acreditación actual.
9. Hoja de ruta con dependencias reales, disponibilidad de código/datos y declaración de contribuciones/uso de IA.

Apéndice reproducible: manifiesto de archivos/hashes, versiones, scripts de análisis, datos agregados con permisos, casos negativos, evidencia del gate y tabla afirmación→fuente→alcance. El autor humano revisa cada cifra, firma la responsabilidad editorial y escoge venue/repositorio público. `PREPARED` nunca equivale a publicado.

## Criterio de “listos para escribir” y “listos para publicar”

Se puede escribir ahora el borrador de arquitectura, citando la evaluación local como preliminar y mostrando los bloqueos. Para declararlo listo para publicar: snapshot final consistente, revisión técnica completa, derechos/licencia ratificados, referencias verificadas, paquete reproducible revisado desde otra máquina y aprobación de autores reales. Para añadir afirmaciones de efectividad científica o validación universitaria: completar además B/C y la evaluación correspondiente. No se fijan fechas ficticias para dependencias institucionales.
