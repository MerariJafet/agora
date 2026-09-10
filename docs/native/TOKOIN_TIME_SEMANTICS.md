# Semántica e inventario temporal V0.2

La única entrada temporal monetaria es RequestFinalizeBlock.time.seconds autenticada por CometBFT; Prepare/Process usan tiempo propuesto para comprobación, CheckTx usa último tiempo comprometido. Store sólo persiste el valor recibido; ProtocolTime rechaza retroceso y tipos inválidos. No existe expiración de transacción, cambio dinámico de validadores ni deadline institucional en esta aplicación nativa: no se simulan como pruebas existentes.

El workflow científico central AGORA conserva relojes de servidor para coordinación/eventos. No son fuente soberana de maduración o balances de TOKOIN. Su influencia sobre propuestas de autorización es explícita: dos revisores deben verificar expediente, y consenso aplica reglas monetarias separadas. No equivale a afirmar que toda AGORA carece de relojes locales.

Inventario ejecutable: native/tools/time_policy.py; resultado audit/local-alpha-v02/iteration-2/time-audit.json. Clasifica coincidencias de tiempo en código first-party. Prohíbe imports/dynamicaccess en core.py/protocol_time.py. Revisión manual del adaptador: timestamp de request, sin consulta de reloj; Store: persistencia sin generación temporal. Dependencias de motor/criptografía no quedan demostradas por un escaneo lexical Python.

Pruebas TIME001–006: guard AST y fronteras/retroceso/salto en suites nativas. TIME009: reinicio antes/en unlock y replay exacto. TIME010: replay por Store y campaña científica. TIME007/008: votos remotos ±60s en red, **cobertura parcial**, no virtualización de reloj completo del validador. No se cambió reloj del host. Ningún test acelerado demuestra 365d reales.

Si cadena se detiene, no se compromete una nueva transición de finalización aunque el reloj humano avance. La UI puede mostrar estimación pero no desbloquear. block timestamp no selecciona ganadores,reviewers ni desempates; éstos siguen identidades/orden canónico.
