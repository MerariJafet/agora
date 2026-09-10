# Verificación de génesis

Verificar dos objetos: génesis CometBFT completo (consenso/tiempos/public keys/poder) y app_state TOKOIN. El hash de dominio del segundo es `digest("tokoin.genesis.v2", app_state)`, no SHA256 del archivo con espacios. Las transacciones V3 incluyen ese hash además de chain_id.

Confirmar TEST_NON_RECOGNIZABLE,8decimales,1,000,000máximo,500capTEST,0premine,versiones y participantes públicos. No editar génesis después de comenzar. Redes nuevas usan génesis nuevo; el journal antiguo se conserva con su binario de baseline. No existe importación económica automática.

Para export verificable: `PYTHONPATH=native python native/tools/verify_export.py EXPORT.json --expected-genesis-hash HASH_APROBADO`. El hash aprobado debe obtenerse por canal independiente; leerlo del mismo archivo no autentica el archivo.
