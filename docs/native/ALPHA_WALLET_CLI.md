# Operación wallet CLI local alpha

Esta CLI usa exclusivamente el contenedor de `wallet_file.py`, vinculando cadena y
hash del génesis. Es offline y TEST: no consulta saldos ni transmite transacciones.
Las claves de consenso del nodo se mantienen fuera del flujo de wallet monetaria.
No admite contraseñas en argumentos ni variables de entorno; solicita la contraseña
mediante `getpass` y aborta si el terminal solo permite entrada con eco.

Desde la raíz del repositorio, usando rutas elegidas por el operador:

```bash
PYTHONPATH=native .venv/bin/python -m tokoin_native.wallet_cli create --genesis /ruta/genesis.json --wallet /ruta/privada/wallet.json
PYTHONPATH=native .venv/bin/python -m tokoin_native.wallet_cli address --genesis /ruta/genesis.json --wallet /ruta/privada/wallet.json
PYTHONPATH=native .venv/bin/python -m tokoin_native.wallet_cli backup --genesis /ruta/genesis.json --wallet /ruta/privada/wallet.json --destination /ruta/backup/wallet.json
PYTHONPATH=native .venv/bin/python -m tokoin_native.wallet_cli restore --genesis /ruta/genesis.json --wallet /ruta/backup/wallet.json --destination /ruta/privada/restaurada.json
PYTHONPATH=native .venv/bin/python -m tokoin_native.wallet_cli sign --genesis /ruta/genesis.json --wallet /ruta/privada/wallet.json --nonce 1 --kind transfer --payload /ruta/transferencia.json --output /ruta/firmada.json
```

Las rutas son ilustrativas. Crear previamente directorios privados; los archivos
nuevos se crean 0600 sin sobrescribir destinos. El génesis requerido es el objeto
completo del protocolo TOKOIN, no únicamente chain_id ni el envoltorio de CometBFT.
La creación solicita confirmar la contraseña. Backup y restore verifican el origen
cifrado antes de copiarlo, conservando identidad y contenido.

`transferencia.json` debe contener exactamente `to` (dirección TOKOIN válida) y
`amount` (entero positivo de unidades mínimas). La CLI valida el formato y rechaza
campos JSON duplicados. El nonce se obtiene de una lectura independiente del estado
verificado y debe ser el siguiente del remitente. Esta CLI no comprueba el saldo,
nonce actual ni finalidad de cadena: la validación del nodo sigue siendo obligatoria.

Antes de firmar muestra en stderr cadena, génesis, dirección, nonce, destinatario e
importe en unidades mínimas. El stdout contiene solo metadatos públicos y ruta del
archivo firmado, con `broadcast: false`. Un archivo firmado permite ejecutar la
transacción autorizada: aunque no contiene la clave privada, debe manejarse con
cuidado. La CLI actual permite firmar transferencias, no decisiones institucionales
ni transacciones administrativas. No hay operación de envío.

## Segunda iteración: defectos corregidos

1. El contenedor seguro no tenía todavía un recorrido CLI integrado: se agregó sin
   recurrir al PKCS8 heredado que carece de vínculo autenticado al génesis.
2. `getpass` puede degradarse a entrada visible: esa advertencia ahora es un error.
3. JSON ambiguo con claves duplicadas: rechazado antes de firma.
4. Los errores estándar de argparse pueden repetir argumentos sensibles: la CLI
   devuelve un error genérico sin repetir valores proporcionados.
5. La previsualización incluye destinatario e importe, además de identidad de red.
6. Backup/restauración usan una sola lectura autenticada: la identidad mostrada es
   la del contenido copiado, evitando desacuerdo por releer un origen sustituido.
7. La auditoría posterior reprodujo RecursionError con JSON de 40,001 bytes y
   20,000 niveles. Ahora se convierte en rechazo controlado antes de pedir contraseña.
   Regresión incluida en `audit/local-alpha-v02/wallet/final-audit-tests.txt`.

Pruebas: `native/tests/test_wallet_cli.py`, incluyendo firma aceptada por transición
real del protocolo, exclusividad del archivo, backup/restauración, cambio de génesis,
contraseña incorrecta, confirmación distinta, entrada con eco y secretos en errores.
Evidencia conjunta: `audit/local-alpha-v02/wallet/iteration-2-tests.txt`.

No se generaron ni migraron wallets económicas. Las pruebas automatizadas sustituyen
la entrada getpass por contraseñas de fixture; la prevención de eco se prueba por su
advertencia real, y no equivale a certificar todos los terminales del sistema.
