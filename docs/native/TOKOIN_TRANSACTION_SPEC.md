# Transacciones nativas

El sobre contiene exactamente `protocol_version`, `genesis_hash`, `chain_id`, `kind`, `sender`, `payload`, `payload_hash`, `public_key`, `nonce` y `signature`. Ed25519 firma el dominio `tokoin.transaction.v3`, un separador NUL y el JSON canónico de todos los campos salvo la firma. La clave pública ocupa 32 bytes y la firma 64, ambas codificadas en hexadecimal minúsculo.

El nonce es un entero secuencial por dirección. Se rechazan replay, identificadores de cadena distintos, campos inesperados y cantidades de punto flotante. La aplicación limita cada transacción a 64.000 bytes y cada bloque a 1.000 transacciones y 1.000.000 de bytes canónicos. La validación de entradas también debe rechazar estructuras excesivamente anidadas sin cerrar la conexión ABCI.

Los tipos implementados son `review_commit`, `review_reveal`, `authorize`, `challenge_submit`, `challenge_decide`, `challenge_appeal`, `invalidate_finalized`, `finalize` y `transfer`. Todas las transacciones llevan firma. La transición no consulta AGORA ni obtiene documentos científicos desde la red.

El compromiso de revisión vincula la autorización completa, el veredicto y una sal de 32 bytes que permanece secreta hasta la revelación. Deben existir dos compromisos de claves y grupos distintos antes de revelar. La autorización exige ambos veredictos compatibles. Una transferencia sólo puede gastar saldo finalizado, nunca una recompensa bloqueada.

La admisión y resolución de una impugnación requieren dos firmas institucionales sobre `chain_id`, `genesis_hash`, `protocol_version`, `reward_id`, `reward_hash`, `challenge_id`, `challenge_revision` y `outcome`, dominio `tokoin.challenge.decision.v3`. Presentar una denuncia no equivale a admitirla. No existe una transacción administrativa para emitir, modificar balances o alterar los límites monetarios.

`PrepareProposal` filtra transacciones sobre una copia del estado y las evalúa en secuencia. `ProcessProposal` rechaza una propuesta inválida. `FinalizeBlock` ejecuta el bloque decidido, y `Commit` persiste el resultado de forma atómica. El estado confirmado y el provisional deben mantenerse separados durante reinicios y reintentos.

Envelope TOKOIN_TX_V3. payload_hash usa digest tokoin.payload.v3; genesis_hash usa digest tokoin.genesis.v2. JSON UTF-8, claves ordenadas, sin espacios, ASCII escapado según canonical; sólo tipos admitidos sin float. CheckTx no reserva nonces: duplicados simultáneos pueden superar consulta preliminar, pero PrepareProposal/ejecución sólo permiten consumir una vez. Cambiar versión requiere génesis alpha nuevo.
