# Operación de nodo — alpha local TEST

Este candidato escucha ABCI exclusivamente en loopback y se ejecuta sobre CometBFT0.38.26. El arnés de cuatro nodos es un laboratorio; no es un instalador público ni demuestra independencia administrativa.

1. Obtener el commit y manifest congelados del Evidence Pack. Verificar antes de ejecutar.
2. Crear entorno Python separado e instalar native/requirements.txt; construir motor con native/tools/build_cometbft.py y comparar hashes.
3. Ejecutar native/tools/chaos_network.py siguiendo chaos_README.md para reproducir red aislada.
4. Para nodo manual, generar configuración propia con cometbft init; revisar génesis común, chain_id TEST, public keys/poder y endpoints. Iniciar aplicación con `PYTHONPATH=native python -m tokoin_native.abci_server --help` y motor con home exclusivo.
5. Verificar altura y AppHash a la misma altura canónica, no comparar latest de nodos a alturas distintas. Nunca aceptar un RPC como prueba de propiedad sin verificar bloques.

Pendiente para operadores externos: instalación por terceros, direccionamiento/TLS/túneles, límites de exposición y ensayo en máquinas independientes. No abrir RPC/ABCI a Internet con esta guía.
