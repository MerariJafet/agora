# Resultados de primera iteración — corte previo a segunda iteración

Baseline inmutable: `569e4ca2b28a4dd90dfe3b5cdf342451477248c8`. Red exclusivamente TEST_NON_RECOGNIZABLE. CometBFT 0.38.26 sin cambios al motor. No emisión económica ni migración de saldos históricos.

## Evidencia observada
- Dos defectos reproducidos antes de corregir: replay de firma entre génesis distintos con mismo chain_id y truncamiento de última fila del journal aceptado. Evidencia: baseline-defects.json.
- 34 pruebas de hardening PASS, incluyendo dominios de firma, maduración, apelación acotada, invalidación posterior sin confiscación y terminaciones reales de procesos en puntos de persistencia. Evidencia hardening.txt/xml.
- 100,000 secuencias monetarias PASS: 400,000 transiciones firmadas, 200,000 aceptadas y 200,000 rechazadas conforme a protocolo; cero errores. Distribuciones y límites contrastados con referencia entera. No equivale a exploración exhaustiva.
- Seis escenarios científicos por API aislada PASS. Trabajadores Python sintéticos; no universidades reales ni revisión humana. El puente de asentamiento nativo aún requiere prueba integrada.
- Wallet cifrada ligada a cadena/génesis: 16 pruebas PASS; falta cerrar operación por CLI.
- Red de cuatro procesos: campaña de caos todavía en ejecución a este corte. Fallos anteriores de arnés se conservan. No se declara PASS completo anticipado.

## Defectos corregidos
Firma V3 incluye génesis, protocolo, emisor y hash de payload; journal verifica cabeza durable y hashes de estado anterior/siguiente; reloj de protocolo explícito y unlock_at persistido; duplicado de evidencia no se evade cambiando método; apelación limitada a una con revisión firmada; invalidación posterior conserva balances; redondeo determinista para importes mínimos.

## Hallazgos que originan segunda iteración
1. Identidad del proveedor de revisión Python no cabe en el contrato anterior codex/claude: corregir esquema, migración y etiquetado TEST, conservando compatibilidad.
2. Completar expediente API → manifiesto nativo → reward → impugnación → maduración simulada → transferencia, sin atribuir validación humana.
3. Añadir CLI de wallet cifrada y pruebas de recuperación operativa.
4. Completar campañas de red adversarial, almacenamiento lleno/solo lectura y repetición desde fuente congelada.
5. Integrar controles CI, documentación operativa, límites y evidencia reproducible.

Decisión de este corte: NO-GO para exposición pública, red económica y mainnet. Resultados parciales de laboratorio verificables; el cierre consolidado incorporará campañas pendientes sin modificar este documento.
