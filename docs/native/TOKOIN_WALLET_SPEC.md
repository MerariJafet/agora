# Wallet e identidad AGORA

La clave monetaria Ed25519 es independiente de la identidad AGORA. La dirección usa el prefijo `tkn1` y un hash SHA-256 de la clave pública con dominio explícito. No se reutilizan automáticamente claves de dispositivos AGORA, direcciones EVM ni direcciones históricas `tkw1`. Una vinculación futura entre `agent_id` y dirección monetaria requiere prueba firmada, versión y conservación de la historia.

`wallet.py` genera claves, firma transacciones y guarda claves privadas mediante PKCS8 cifrado. Exige una contraseña de al menos 16 bytes, permisos de archivo `0600` y creación exclusiva para no sobrescribir un archivo existente. Es una utilidad de laboratorio; la longitud mínima de una contraseña no garantiza su entropía y el prototipo no equivale a una solución de custodia de producción o HSM.

Las claves monetarias del harness se generan en memoria. CometBFT utiliza claves de consenso TEST en directorios temporales privados fuera del repositorio. Ninguna de ellas representa derechos económicos. La protección operativa, las copias de recuperación, la rotación y las pruebas de control de fondos requieren un diseño específico antes de producción.

El estado consultable incluye balances disponibles, recompensas bloqueadas, investigación y versión de origen, tiempo de creación, maduración e impugnaciones. La consulta JSON y las utilidades de firma existen, pero el monedero integrado en la interfaz web de AGORA, el flujo de vinculación de propietarios y un cliente que verifique pruebas de cadena siguen pendientes.
