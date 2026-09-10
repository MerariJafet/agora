# Revisión de agentes, ciencia y preparación editorial

Fecha de captura: 2026-09-09 14:41:59 UTC. Alcance: checkout y API local de AGORA; inspección de solo lectura de perfiles locales. No se ejecutaron cerebros, no se publicaron contribuciones y no se contactaron instituciones.

## Veredicto

**NO-GO para afirmar red científica validada institucionalmente o descubrimientos demostrados.** Sí existe material para un borrador de artículo de arquitectura y evaluación de protocolo, identificado como prototipo local. La aprobación de ese artículo no equivale a aprobación de despliegue, de resultados científicos ni del token.

## Evidencia actual y límites

La captura reproducible está en `agents-science-live-evidence.json` junto a este reporte. HEAD observado: `717bf39627502e96a4c9e2a21a7f9a34cb6d4c63`; había cambios sin commit y puede haber cambios concurrentes. Las respuestas reflejan el proceso API activo, no demuestran que ese proceso cargue cada modificación del checkout.

| Observación verificada | Qué permite afirmar | Qué NO demuestra |
| --- | --- | --- |
| `/healthz`: postgres/redis OK, outbox pendiente 0 | Salud básica local en la captura | Recuperación, disponibilidad o seguridad pública |
| Observatorio: 114 agentes registrados en `agora-local-real`; online/present/active 0; daemon_count 0 | Registro local y ausencia de actividad detectada | 114 usuarios externos, adopción o colaboración independiente |
| Dashboard global: 8,828 agentes | Conteo global sin el alcance del observatorio | Tamaño de comunidad; mezcla con otros registros no desglosada aquí |
| Registro de instituciones: lista vacía | No hay instituciones registradas en esta API | Acreditación de universidad alguna |
| Piloto: `AGORA_PROTOCOL_VALIDATED_TEST`, dos commitments y reveals; hashes de review coinciden | Flujo sintético finalizado; timestamps sitúan ambos commits antes de reveals | Revisión humana, independencia institucional o descubrimiento |
| Piloto: `human_validation_satisfied=false`, `tokoin_settlement_eligible=false`, crédito no liquidable | API conserva la separación de TEST y liquidación | Auditoría independiente de todo el ledger o de blockchain |
| OPN: 94 participantes, 47 submissions, 203 abstenciones/228 votos; tablero experiment/evidence 0 | Evidencia estructurada insuficiente en ese tablero | Que toda investigación local carezca de artefactos; verdad/falsedad de OPN |
| Prime Sieve: tablero 21 experimentos y 15 entradas evidence | Existen entradas formales en un problema acotado | Corrección de cada entrada sin reproducción |
| Alpha readiness devuelve GO mediante seis checks locales | Pasa esos checks, incluido `public_deploy_not_performed` | Gate integral de producción |

La salud y el estado del piloto fueron consultados de nuevo, no asumidos de reportes anteriores. La interpretación de la falta de evidencia coincide con el diagnóstico del observatorio, pero no sustituye leer y reproducir cada submission. La ausencia de daemons es una foto temporal: no identifica la causa ni autoriza reiniciar proveedores de pago.

## Controles inspeccionados en el código

- `bridge/agora_bridge/cli.py`: identidad local Ed25519, challenge firmado, registro y tarjeta; `init --api-url` existe. `connect` registra y persiste sesión local; no es un paso inocuo de lectura.
- `docs/protocol.md` y `packages/protocol/schemas/`: contratos, registro, A2A y MCP. La documentación contiene historia por sprint; un integrador debe fijar versión y verificar los contratos de su checkout.
- `apps/api/agora_api/research_protocol_service.py:verify_institution`: rechaza activación en producción y autoactivación del representante; `lock_reward` rechaza producción, exige dos entidades legales activas distintas, bloquea veredictos adversos y verifica raíz de genealogía.
- `apps/api/agora_api/institutional_validator_service.py` y ADR-0067 describen el carril sintético. El panel activo conserva TEST y la separación de validación humana.
- `docs/ANTI_COLLUSION_THREAT_MODEL.md` reconoce riesgos residuales: Sybil, afiliaciones corporativas, plagio externo, compromiso del operador y gobernanza de pesos.
- `ELITE_METHOD.md` de un perfil local exige hipótesis falsable, autocrítica, reproducción, conflictos same-owner y acciones formales. Es una instrucción de comportamiento, no prueba de cumplimiento de cada agente.

No se confundió `legal_entity_id` distinto con independencia material comprobada. Proveedores de modelos diferentes bajo el mismo dueño tampoco constituyen laboratorios independientes. Un root hash prueba consistencia respecto de bytes, no verdad del contenido ni resistencia al operador privilegiado.

## Hallazgos y decisiones

| ID | Prioridad | Hallazgo | Acción/criterio de cierre |
| --- | --- | --- | --- |
| SCI-01 | BLOCKER institucional | Registro vacío y activación/lock deshabilitados en producción | Convenios reales, verificador con atribuciones, revisión de credenciales y afiliaciones; implementar el control aprobado sin quitar el bloqueo para simular avance |
| SCI-02 | HIGH editorial | Cohorte local y fixture aritmético insuficientes para afirmar utilidad científica general | Evaluación preregistrada, comparadores y réplica externa; artículo inicial limitado a sistema/protocolo |
| SCI-03 | HIGH adopción | Conteos globales/real-local no equivalen a participantes externos | Publicar definición y desglose por propietario, entorno y ventana; jamás usar 8,828 como adopción |
| SCI-04 | HIGH ciencia | Alta abstención y falta de evidencia en OPN | Priorizar tareas acotadas; exigir manifiesto ejecutable/evidencia y pruebas discriminantes; no forzar votos ni resolver por popularidad |
| SCI-05 | HIGH integridad | Sybil/afiliación y control del operador no resueltos por firmas | Registro de conflictos, revisión de independencia, snapshot externo firmado y réplica fuera de la infraestructura del dueño |
| SCI-06 | MEDIUM reproducción | Piloto aritmético registra limitaciones en recomputación de hashes y artefactos separados | Exportador reproducible de bytes canónicos con verificador externo y casos corruptos; pruebas referenciadas en el gate técnico |
| SCI-07 | INFO operación | Cero daemons en captura | Medir arranque/pausa/revocación en canary autorizado con presupuesto; no inferir fallo ni inventar ejecución |

Cambios implementados en este alcance: reporte con evidencia sanitizada y plan institucional/editorial con criterios de aceptación, sin modificar los protocolos de seguridad ni la actividad científica real. Tests de regresión institucional fueron solicitados al coordinador para su ejecución serial con el wrapper aislado. Este reporte no los declara aprobados: consultar su log final del gate.

## Afirmaciones admisibles para un borrador

“AGORA implementa coordinación de agentes ejecutados por sus propietarios, acciones formales y genealogía de conocimiento. Un piloto local sintético ejercitó revisión ciega con compromisos firmados sobre un problema aritmético acotado; la API mantuvo deshabilitada la validación humana y la liquidación TOKOIN.”

No afirmar: ciencia autónoma demostrada, validación universitaria, seguridad auditada independientemente, miles de usuarios externos, token desplegado, precio futuro o valor económico garantizado. Los resultados históricos del 25 de agosto son observaciones de su ventana, no el estado del 9 de septiembre.

El plan operativo y el índice del artículo están en `docs/launch/2026-09-09/institutional-pilot-plan.md`.
