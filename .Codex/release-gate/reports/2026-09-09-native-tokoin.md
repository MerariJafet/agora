# RELEASE SECURITY GATE — TOKOIN nativo

Fecha: 2026-09-09. HEAD: 717bf39627502e96a4c9e2a21a7f9a34cb6d4c63. Fingerprint: 99f4ded0bf38e3840c466ef86e7c5e6f49564b2028252fdf0a31a17e3306c9e5.
Destino evaluado: red pública/economía real. Entorno ejecutado: laboratorio local TEST.

## Veredicto: NO-GO público/económico

Resultado técnico: red TEST real de cuatro motores CometBFT 0.38.26 y cuatro aplicaciones ABCI2 funcional, sin Ethereum/Base/PostgreSQL soberano para balances. El plan maestro completo NO está terminado. No se emitieron asignaciones económicas reconocidas ni se convirtió el ledger existente.

## Evidencia ejecutada

- 35 pruebas nativas PASS; incluyen 1000 casos de reparto generados, firmas, límites, replay, doblegasto,365d simulado, impugnaciones, versiones, reinicios y persistencia.
- 25 regresiones AGORA PASS mediante scripts/run-isolated-tests.sh, con DB de prueba aislada.
- Ruff repositorio PASS; mypy 8 módulos nativos PASS.
- pip-audit sobre native/requirements.txt: No known vulnerabilities found. No afirmar auditoría independiente de toda la cadena de dependenciasGo.
- CometBFT fijado a commit 94d77f9f51a72e2b7d832798859f6222f08028f8; Go oficial y SHA verificados; dos builds locales idénticos.
- Red real: bloques vacíos, revisiones commit/reveal,1 TOKOIN TEST locked, replay/earlyfinality/lockedspend rechazados,3/4 nodos avanza,2/4 detiene,quórum recuperado,nodo rezagado resincronizado,reinicio de aplicación,igual bloque y raíz.
- Replay desde exportación en 3 procesos con semillas de hash distintas: mismo estado/manifiesto. Otra máquina/operador: NOT_RUN.
- Última altura común verificada 15, blockhash9047F74D7C062621E58661202BA51D0EF97385D5B3B1A7731613B6E476605293.
- Procesos del harness detenidos al terminar; API AGORA original sana.

## Hallazgos reproducidos y correcciones

NT-01 HIGH — JSON anidado de 2201 bytes provocaba RecursionError y podía cerrar conexión ABCI. Se normaliza a Invalid, limita estructura y prueba TCP que rechaza y sigue atendiendo. FIXED.

NT-02 MEDIUM — Merkle con duplicación de última hoja permitía igual raíz para tres/cuatro hojas. Root V2 incluye cantidad. Prueba de regresión PASS. FIXED.

NT-03 HIGH — Una denuncia SUBMITTED con sólo hashes podía bloquear fondos gratuitamente. Ahora sólo ADMIT con dos firmas pausa; denuncia permanece en historia sin efecto monetario automático. FIXED para ese vector; censura de admisión/apelación institucional sigue HIGH OPEN.

NT-04 HIGH — Génesis de app no anclaba claves de consenso. Añadido conjunto al génesis de app y comparación en InitChain; hash del génesis CometBFT completo registrado. FIXED en arranque TEST. Cliente ligero/certificados de consenso para manifiesto económico: UNKNOWN.

## Bloqueantes restantes

1. Instituciones reales, identidad, independencia y mandato delegado no acreditados; registro TEST no es validación humana.
2. Anti-Sybil/plagio/farming, scoring, financiación de revisión adversa y operadores, admisión/apelación anticensura y gobernanza no cerrados.
3. UI de wallet y enlace institucional completos, cliente verificador con pruebas y recuperación de claves pendientes. Explorer entregado es instantánea local.
4. Auditoría externa, operadores/máquinas independientes, particiones y fallos bizantinos ampliados, recuperación catastrófica y génesis económico firmado e importador auditado pendientes.
5. Ninguna maduración real de 365 días se ha demostrado. El dominio TEST se rechaza para reconocimiento económico; manifiestos TEST reconocen cero.

## Rollback y preservación

Cambios nativos aislados en native/, docs/native/ y audit/native-2026-09-09; CI añade pruebas. Sin migración sobre DB activa ni alteración de balances. Journal local tiene persistencia atómica/replay; no afirmar rollback de bloques finalizados ni permitir confiscación. Artefactos de red conservados en directorio TEST privado fuera del repo. No publicar sus claves.

## Decisión

Apto para continuar ingeniería local y pruebas técnicas delimitadas. No cumple todavía todas las fases 0–7 ni la definición de piloto económico. La skill release-gate exige «NO EVIDENCE → NO PASS» y controles críticos UNKNOWN fuerzan NO-GO. Se conserva ese gate; no se pide aprobación para saltarlo.

Artefactos: docs/native/IMPLEMENTATION_STATUS.md; docs/native/TOKOIN_MAINNET_READINESS_CHECKLIST.md; audit/native-2026-09-09/summary.json; network-test.json; unit-results.xml; independent-process-replay.json; explorer.html.
