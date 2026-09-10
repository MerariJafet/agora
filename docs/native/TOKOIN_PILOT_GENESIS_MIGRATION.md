# Migración que conserva la historia

El legado PostgreSQL/EVM permanece separado. El millón asignado a tesorería y los repartos históricos no se transforman automáticamente en emisión nativa. Se mantienen sus identificadores, dominios e hashes originales. Sólo recompensas que cumplan autorización, identidad acreditada, integridad y maduración aplicable podrían considerarse para un reconocimiento económico futuro.

El cierre de un piloto reconocible exige fijar una altura y el génesis completo, detener nuevas admisiones conforme a una regla pública, verificar bloques y certificados, y reconstruir recompensas, impugnaciones y asignaciones. Debe comprobarse el límite de 500 TOKOIN sin añadir saldos que carezcan de prueba. Los estados bloqueados y revocados se preservan por separado.

La instantánea debe ser canónica y reproducible. Su árbol de balances usa direcciones ordenadas y el compromiso Merkle de versión 2, que incluye la cantidad de hojas. Operadores independientes verifican la instantánea y las autoridades distribuidas definidas para la migración firman el manifiesto. No se modifican asignaciones mediante una hoja manual ni se incorporan distribuciones ocultas.

`Store.manifest()` implementa únicamente una exportación determinista TEST. Incluye raíces de historia, estado y balances, recompensas e impugnaciones. Su etiqueta es `PILOT_GENESIS_MANIFEST_TEST_ONLY`, `recognized_economic_units` vale cero y `genesis_recognition_eligible` es falso.

Ese artefacto no es un manifiesto económico firmado, un certificado de finalidad CometBFT ni el cierre de un piloto reconocible. Su journal debe vincularse a bloques certificados y al génesis completo para verificar consenso. El importador económico no está habilitado. Dos procesos locales que producen la misma raíz no equivalen a dos auditores o universidades independientes.

Si se reconocieran exactamente 500 TOKOIN válidos y no hubiera creación revocada adicional que consumiera el límite, quedarían 999.500 por emitir. La cifra está sujeta a la política definitiva de reconocimiento y creación acumulada; no autoriza reconocer ahora los saldos TEST.
