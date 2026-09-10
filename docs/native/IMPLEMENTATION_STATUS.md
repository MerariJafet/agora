# Aplicación del plan maestro — entrega técnica local

Se implementó incrementalmente una cadena TEST con motor CometBFT oficial y aplicación monetaria propia, sin reconstruir AGORA. La red funciona sin Ethereum/Base y no consulta PostgreSQL para validar saldos. Se conserva el legado SQL/EVM y su política histórica.

## Implementado

- Descubrimiento y 15 especificaciones de arquitectura, moneda, consenso, génesis, wallet, ciencia, seguridad y migración.
- Tres modelos monetarios, cuatro escenarios y 100 años por escenario; precisión entera y horizonte 10/25/50/100.
- Núcleo monetario: cero preminado, cap 1 M, cap piloto 500, reparto 10/10/51/20/9 versionado, firmas Ed 25519, nonces, compromiso de reviews y reparto, lock 365 d, challenge y revocación histórica.
- Motor 0.38.26 compilado desde commit fijado; descarga verificada y dos builds locales con hash idéntico. Bindings oficiales ABCI 2 y procedencia de dependencias.
- Red de cuatro motores con cuatro aplicaciones: bloques vacíos, emisión TEST locked, rechazo de replay y gasto prematuro, pérdida/recuperación de quórum, reinicio y sincronización.
- Journal atómico que se reproduce desde génesis; génesis compromete claves de consenso y el adaptador comprueba su correspondencia inicial. La verificación del journal por sí sola no prueba firmas BFT.
- Bridge offline que reutiliza el verificador AGORA y produce borrador sin firmar/enviar; wallet cifrada, consultas de nodo, explorador HTML de instantánea y manifiesto TEST determinista.
- Pruebas nativas incluidas en CI. No se cambió el balance soberano de la aplicación AGORA ni se desplegó públicamente.

## No completar por simulación ni por etiqueta

El plan maestro completo sigue parcialmente abierto. No hay integración de producto terminada de las pantallas AGORA, registro de instituciones reales, mandato delegado definitivo, scoring anti-Sybil/plagio, financiación de revisión adversa y nodos, defensa anticensura de admisión, gobernanza auditada ni importador económico de génesis.

Tampoco existen operadores/máquinas independientes en esta prueba, auditoría externa o 365 d de maduración económica. Son condiciones distintas de que cuatro procesos locales puedan acordar bloques. No se presenta el manifiesto TEST como asignación económica candidata válida ni se reconocen automáticamente tokens históricos.

Siguiente prioridad técnica: completar el adaptador institucional y el flujo de wallet/cliente verificador con pruebas de cadena, seguido de prueba entre operadores independientes. Antes de habilitar dinero real, resolver admisibilidad y apelación sin permitir bloqueo gratuito ni supresión de evidencia válida. La matriz completa está en TOKOIN_MAINNET_READINESS_CHECKLIST.md.
