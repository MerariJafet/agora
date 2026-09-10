# Backup y recuperación

Wallet: usar contenedor cifrado wallet_file/CLI, password por terminal, archivos0600 y backup validado con chain_id/génesis. No subir claves ni passwords a Evidence Pack. Probar restauración antes de depender del backup.

Nodo: parar coordinadamente motor y aplicación; copiar directorios completos a almacenamiento privado con hash, incluyendo journal WAL/SHM cuando corresponda y estado de firma del motor. Preferir backup SQLite consistente o apagado limpio; no copiar sólo .sqlite durante escritura. Mantener software/génesis exactos.

En recuperación verificar journal desde génesis, durable_head y AppHash contra nodos honestos. Si faltan filas o hashes no coinciden: fallar cerrado, preservar archivos, reconstruir desde bloques verificados. No editar balances/cabeza durable para borrar el error. Snapshots ABCI se rechazan: sincronización soportada reproduce bloques desde génesis.
