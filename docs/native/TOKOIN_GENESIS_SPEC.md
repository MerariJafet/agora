# Génesis y anclaje de consenso

El génesis de aplicación compromete la versión, el modo `TEST_NON_RECOGNIZABLE`, un `chain_id` con prefijo `tokoin-test-`, la unidad mínima, los límites monetarios, los 365 días, el monto experimental fijo, el reparto, el registro institucional TEST y la dirección de infraestructura. Incluye además `consensus_validators`: las claves públicas y poderes del conjunto inicial de validadores blockchain.

La serialización es JSON ASCII ordenado y compacto, sin cantidades de punto flotante. Los hashes usan SHA-256 con un dominio explícito y separador NUL. Los registros y parámetros son públicos; el génesis no contiene claves privadas ni un saldo preminado.

CometBFT dispone de su propio archivo de génesis, que incorpora el estado exacto de la aplicación, los validadores, el tiempo y los parámetros de consenso. Deben distribuirse y fijarse tanto su hash completo como el hash de aplicación. `InitChain` verifica el estado, el identificador de cadena, la altura inicial, el tiempo y la igualdad del conjunto de validadores recibido con `consensus_validators`; exige al menos cuatro validadores para esta red de prueba.

Los fixtures unitarios pueden construir una máquina de estados sin un conjunto operativo de consenso. No cumplen por ello las condiciones de arranque ABCI. Cuatro claves locales tampoco equivalen a cuatro operadores independientes.

El journal rechaza un génesis diferente y reconstruye las raíces al reproducir sus bloques. Esa comprobación valida transiciones; la finalidad blockchain debe verificarse además mediante los bloques y certificados CometBFT. El conjunto inicial incluido en la aplicación no reemplaza esas pruebas posteriores.

La importación de un génesis económico no está habilitada. Antes de implementarla se requieren un manifiesto de migración, identidad real, procedencia, madurez aplicable y verificación independiente. Un manifiesto TEST nunca se convierte en una asignación económica por cambiarle la etiqueta.
