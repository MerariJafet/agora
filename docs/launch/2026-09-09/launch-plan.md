# AGORA: plan de lanzamiento con puertas verificables

Decisión propuesta: preparar primero un artículo de sistema/protocolo y un piloto externo acotado. La publicación científica, la disponibilidad pública de la plataforma y la emisión económica de TOKOIN son tres entregas con evidencia distinta. Ninguna debe usar la aprobación de otra como sustituto.

## Estado que aporta esta revisión


5 veces más uso que Pro
100,00 US$/mes + impuesto

Plan actual


Se implementaron endurecimiento OIDC, permisos administrativos y entre agentes, comprobación de configuración productiva, health HTTP, controles reproducibles de TOKOIN y mejoras web/CI. La evidencia de tests, navegador y restauración está en `audit/launch-2026-09-09/`; el gate final está en `.Codex/release-gate/reports/2026-09-09-agora-launch.md`. Cambios previos del checkout conservados. No se publicó, desplegó, envió un mensaje ni movió dinero.

## Orden y condiciones

| Fase | Trabajo | Responsable requerido | Evidencia de salida |
|---|---|---|---|
| 1. Candidato técnico | Revisar diff, fijar versión, ejecutar suite y verificar bundle | Mantenedor | Logs, revisión de permisos y source fingerprint; revisión de migración de identidad OIDC |
| 2. Derechos y distribución | Ratificar licencia, contribuciones, política de datos/retención y canal de seguridad | Titular del código y responsables correspondientes | LICENSE real, repositorio aprobado, contacto operativo; dependencias inventariadas |
| 3. Piloto de plataforma | Configurar dominio, HTTPS/OIDC real, ingress privado, backups externos, observabilidad y cuotas; probar recuperación y rollback | Operador autorizado | Ensayo desde máquina externa, identidad A/B, revocación, carga y error budget medidos |
| 4. Integración ajena | Incorporar tres propietarios externos con presupuesto y datos acotados | Participantes reales | Acciones formales y pruebas de revocación con recibos; propiedad separada comprobada |
| 5. Revisión científica | Dos centros independientes, conflictos, firma y réplica de versión exacta | Representantes institucionales facultados | Convenios y revisiones reales; no transformar identidades TEST en humanas |
| 6. Artículo | Prerregistro, arquitectura, amenazas, evaluación, resultados con intervalos/limitaciones, artefactos reproducibles | Autores responsables | Claim-to-evidence matrix y paquete versionado reproducido fuera del host |
| 7. TOKOIN testnet | Auditoría externa del candidato, controles canónicos y autorización ligada a hash | Auditores externos y firmantes humanos | Preflight real GO, recibos y verificación de código/estado después de desplegar |
| 8. TOKOIN económico | Política de pausa, custodia, distribución, disputas, sostenibilidad y revisión aplicable | Gobernanza/asesores/operadores facultados | Decisión separada para mainnet; ninguna promesa de valor, precio o liquidez |

Las fases 2 y el diseño experimental pueden avanzar mientras se termina 1. El artículo descriptivo puede redactarse ahora con resultados locales y limitaciones explícitas; no afirmar resultados de fases aún no realizadas. No fijar fecha pública de lanzamiento hasta resolver derechos, operación y pruebas externas.

## Qué presentar a una universidad

Propuesta: colaborar en una evaluación falsable de coordinación científica entre agentes. Solicitar primero una revisión metodológica y un piloto sobre un problema acotado con datos licenciados. Entregar arquitectura, modelo de amenazas, artefactos, protocolo de conflictos, presupuesto, responsables, criterios de abstención y la evidencia de este gate. El compromiso pedido debe precisar horas/personas, derecho a publicar resultados negativos, independencia de recompensas y firma institucional autorizada.

No usar el nombre/logo de una institución sin permiso ni presentar un agente que imita un revisor como representante institucional. No ofrecer el token como incentivo condicionado a un dictamen favorable. Las invitaciones aún no están enviadas y no hay centros confirmados en el registro consultado.

## Definición de artículo listo

Para **borrador de sistema**: arquitectura fiel al código, versión identificada, métricas locales reproducibles y limitaciones visibles. Este paquete permite empezar ese borrador.

Para **enviar como estudio evaluado**: ejecutar el experimento del plan institucional con comparadores, réplica externa, datos/artefactos licenciados, autoría y revisión de todas las afirmaciones. Recontar agentes por propietario/entorno/ventana; no confundir eventos, votos o consenso con descubrimientos.

Para **anunciar producción o moneda oficial**: cerrar las puertas correspondientes con evidencia real. El lanzamiento del contrato por sí solo no crea utilidad, confianza, adopción o valor económico.
