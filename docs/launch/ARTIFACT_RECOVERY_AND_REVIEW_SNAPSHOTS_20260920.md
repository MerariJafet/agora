# Recuperación verificable y expedientes de revisión — 20 septiembre 2026

## Cambios de código

- Descargas: un contenido ausente, de tamaño incorrecto o cuyo SHA-256 no coincide devuelve HTTP 503 con `error.code=artifact_unavailable` antes de servirlo. El registro y su atribución siguen disponibles; esto no convierte una pérdida de evidencia en un 404 de versión inexistente.
- Subidas: la deduplicación verifica SHA-256 además del tamaño. Una nueva subida de los bytes originales repara un blob corrupto sin modificar versiones previas. El fichero temporal se sincroniza antes del reemplazo atómico.
- Revisión sintética: el primer acceso autenticado materializa el expediente completo bajo bloqueo de la asignación. Lecturas y propuestas posteriores usan esa misma copia, aunque aparezcan nuevas conversaciones. Un trigger PostgreSQL impide modificar o vaciar el expediente ya guardado. Los expedientes de los pares no se revelan.
- Migración aditiva `0046_validator_package_snapshot`: las asignaciones antiguas aún ASSIGNED se materializan en su primer acceso. Una revisión antigua ya iniciada sin copia persistida devuelve conflicto; no se inventa ni actualiza el hash de un expediente que nadie revisó. Para ese caso se requiere una nueva revisión sobre una nueva versión candidata. No hay backfill fabricado.
- `scripts/audit_artifact_store.py` es un auditor offline, sólo lectura. Compara todas las referencias del manifiesto exportado con tamaño, hash y ruta segura. Código de salida 0 significa colección íntegra; 2 significa referencias inválidas, archivos ausentes, corruptos o ilegibles. No confundir 16 archivos correctos con integridad de los 18 registrados.

## Comprobación repetible

Exportar desde una copia consistente de PostgreSQL, sin credenciales en el archivo:

```sql
SELECT coalesce(json_agg(json_build_object(
  'artifact_version_id', artifact_version_id,
  'storage_key', storage_key,
  'content_hash', content_hash,
  'content_size', content_size
) ORDER BY artifact_version_id), '[]'::json)
FROM artifact_versions WHERE storage_key IS NOT NULL;
```

Comprobar una copia consistente del almacén (o pausar uploads durante exportación y comprobación):

```bash
python scripts/audit_artifact_store.py --manifest /ruta/manifest.json --store-root /ruta/almacen > /ruta/integridad.json
```

El auditor no ejecuta ningún artefacto. Nunca copiar una referencia fuera de `sha256/<dos-primeros-caracteres>/<hash>` ni reemplazar metadatos para que una comprobación pase.

## Lo único que requiere originales externos

Solicitar a Saraya los archivos originales subidos el 17 de septiembre, incluyendo backups o historial de su herramienta. No reescribirlos ni cambiar sus finales de línea:

| Archivo | Bytes | SHA-256 |
|---|---:|---|
| saraya_collatz_empirical_audit.py | 6369 | 2416537175086aaaaa2163dd0a848b630f924015d22b1679fe426e550bd7ffc6 |
| verify_euler_conjecture.py | 2154 | 77f97d4cfb460417d8d546ba15870e6daaffea40a52cf1bf3849437cbf95d823 |

El segundo tiene dos referencias de versión. Entregar los archivos como archivos, preferiblemente en ZIP para preservar los bytes. Una coincidencia de nombre no basta. En Windows se puede comprobar con `Get-FileHash -Algorithm SHA256 <archivo>`; en Linux con `sha256sum <archivo>`.

Una vez recibidos, el operador técnico debe verificar tamaño y hash, restaurar únicamente los bytes faltantes en sus claves originales, repetir auditoría completa y descargas públicas, tomar backups coherentes y volver a pasar release-gate. El usuario no tiene que programar ni modificar la base de datos.

## Despliegue y rollback

El volumen persistente ya está versionado en Compose desde PR #26; no se debe reemplazar el contenedor existente con un volumen vacío. Precargar y verificar el almacén antes del corte. Conservar PostgreSQL, el volumen y sus backups al revertir código; no eliminar la columna de snapshots que ya contiene revisiones. La corrección de código no recupera mágicamente bytes perdidos y no concede GO por sí misma. TOKOIN económico y validación institucional humana siguen fuera de este despliegue.
