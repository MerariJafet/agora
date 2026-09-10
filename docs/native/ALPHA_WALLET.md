# Wallet local alpha: contenedor autenticado

Estado: implementado para TEST; no constituye auditoría externa ni custodia de producción.

## Contrato

`tokoin_native.wallet_file` conserva la clave monetaria Ed25519 en un contenedor JSON
versionado, con identidad de cadena, hash del génesis y clave pública. Los tres forman
parte del AAD autenticado mediante AES-256-GCM: recalcular el checksum público no
permite cambiar la red ni la identidad sin conocer la contraseña. El checksum SHA-256
identifica corrupción, mientras que GCM autentica. Se deriva la clave AES mediante
scrypt, N=32768, r=8, p=1, sal aleatoria de 16 bytes y nonce aleatorio de 12 bytes.
Los parámetros se fijan por versión; un archivo no puede elegir un KDF de coste arbitrario.
No se almacena una seed ni clave privada sin cifrar. La contraseña exige 16–1024 bytes;
es un mínimo de longitud, no una garantía de entropía.

API:

- `create_wallet(path, password, chain_id, genesis_hash, key=None)` crea un archivo nuevo.
- `load_wallet(path, password, expected_chain_id, expected_genesis_hash)` verifica red,
  integridad, contraseña e identidad antes de devolver una clave utilizable.
- `Wallet.sign_transaction(genesis, nonce, kind, payload)` verifica el hash del génesis
  antes de delegar en el formato firmado de transacción del protocolo.
- `backup_wallet` y `restore_wallet` autentican el origen y copian los mismos bytes
  cifrados sin reemplazar destinos existentes. La identidad y las firmas se conservan.

El cliente debe mostrar chain_id, hash del génesis y dirección pública antes de firmar.
Las claves de consenso son archivos separados gestionados por el nodo; este módulo
no los descubre ni importa automáticamente. Una importación explícita `key=` queda
bajo responsabilidad del operador y no demuestra que una clave jamás se haya reutilizado.
El API heredado PKCS8 de `wallet.py` permanece separado por compatibilidad; no ofrece
la vinculación de red del nuevo contenedor y no debe usarse en el flujo alpha nuevo.

## Escritura y lectura seguras

El archivo temporal se crea en el mismo directorio con permisos 0600, se escribe
completo y se ejecuta fsync antes de publicarlo mediante hard link atómico que no
sobrescribe. Se sincroniza el directorio después de la publicación. Ante interrupción
el destino está ausente o contiene el contenedor completo; pueden quedar temporales
cifrados 0600, que no equivalen a una wallet parcialmente válida. El directorio debe
ser privado y confiable. La política está dirigida al sistema Linux local y sus
semánticas de fsync/hard link; no promete durabilidad en cualquier almacenamiento remoto.

La lectura rechaza symlinks, archivos no regulares, permisos distintos de 0600 y más
de 4096 bytes. Los errores de autenticación son genéricos; no se imprimen contraseñas
ni material de clave. La representación del objeto excluye la clave privada. Python
no garantiza borrado seguro de secretos en RAM; este módulo no protege frente a un
proceso comprometido, root o contraseñas débiles. El backup sigue siendo sensible,
aunque esté cifrado.

## Resultados ejecutados

Comando: `AGORA_ENV=test PYTHONPATH=native .venv/bin/python -m pytest native/tests/test_wallet_hardening.py -q`

Resultado: **16 passed**. Evidencia: `audit/local-alpha-v02/wallet/pytest.txt`.

| Requisito | Prueba |
|---|---|
| WALLET-001 | Contraseña incorrecta rechazada sin detalles secretos |
| WALLET-002 | Corrupción, versión inválida, checksum incorrecto y sobrelongitud rechazados |
| WALLET-003 | Truncado rechazado |
| WALLET-004 | Backup/restauración conservan bytes cifrados, identidad y firma |
| WALLET-005 | Importar la misma clave conserva identidad con cifrados distintos |
| WALLET-006 | Firma rechazada para otra cadena o génesis modificado |
| WALLET-007 | Salidas, errores y representación capturados no contienen contraseña ni clave de prueba |
| WALLET-008 | Proceso terminado antes/después de publicación; destino ausente o autenticable |
| Adicional | Checksum recalculado no permite reescribir red autenticada |
| Adicional | No sobrescritura, rechazo de symlinks/permisos y fallo de fsync antes de publicación |

Estas pruebas no son una búsqueda exhaustiva de secretos de toda la máquina. No se
crearon claves de producción, ni se imprimieron claves privadas en los resultados.
