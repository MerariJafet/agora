# Verificación de binarios

Motor oficial fijado: CometBFT0.38.26 commit94d77f9f51a72e2b7d832798859f6222f08028f8. SHA256 probado:6edb2aa0f223e71758a48cf3d13d9d7ffd26f3357585bebe54311ba71f11ac3f.

`python native/tools/build_cometbft.py --cache /RUTA/CACHE --report /RUTA/build.json` verifica archivos fuente y Go por hash antes de compilar. `--offline` exige archivos y módulos descargados previamente. No desactivar verificación para hacer pasar el build. Verificar también código Python y auxiliares Go en manifest; motor idéntico no garantiza aplicación idéntica.

Una recompilación en otra carpeta de este PC demuestra repetición local, no reproducibilidad independiente por terceros. No atribuir firma o auditoría humana a hashes generados por la misma sesión.
