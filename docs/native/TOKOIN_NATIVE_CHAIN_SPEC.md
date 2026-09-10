# Cadena nativa TOKOIN: arquitectura de referencia

La versión candidata local utiliza el dominio `TEST_NON_RECOGNIZABLE`, CometBFT 0.38.26 y una aplicación Python ABCI 2.0. PostgreSQL, AGORA y EVM no intervienen en la validación monetaria. Para reproducir balances, el nodo necesita su génesis fijado, el motor, la aplicación y el journal local; no necesita consultar un servidor central de AGORA.

El bloque oficial CometBFT aporta identificador de cadena, altura, enlace al anterior, tiempo, compromisos de datos, identidad del proponente y certificados de validadores. No se modifica el formato del motor para añadir firmas propias. La aplicación conserva raíces de transacciones, estado y compromisos de investigación. El estado científico comprometido forma parte del `app_hash`; la firma y la finalidad se verifican en los bloques CometBFT, no en el journal SQLite aislado.

El `app_hash` de la aplicación después de ejecutar la altura H se incorpora al encabezado siguiente. Las herramientas de comparación deben usar esa correspondencia de alturas. La raíz Merkle de versión 2 incluye el número de hojas para evitar ambigüedad por duplicación de la última hoja.

La transición monetaria es determinista: no usa reloj local, llamadas de red, modelos de lenguaje ni consultas a la base científica. El journal ofrece persistencia atómica y reproducción desde génesis, pero no es un mecanismo de consenso. La sincronización por snapshots está deshabilitada; las ofertas se rechazan y el nodo reproduce los bloques desde génesis.

El génesis de aplicación incluye el conjunto inicial de validadores, que ABCI comprueba durante `InitChain`. Los parámetros y el archivo completo de génesis CometBFT también deben fijarse y verificarse. Las pruebas con cuatro nodos locales demuestran funcionamiento técnico bajo una administración común; no demuestran independencia operacional ni resistencia completa a ataques bizantinos.

No existe una ruta mainnet habilitada. La evaluación de abuso, censura, protección de claves, recuperación, actualizaciones y operación entre organizaciones independientes sigue siendo un requisito previo al uso económico.
