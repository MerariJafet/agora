# Laboratorio local Byzantine / chaos

`chaos_network.py` crea una red TEST nueva por ejecución. Usa CometBFT 0.38.26
con hash binario aprobado, cuatro validadores de igual poder y aplicaciones
separadas. Solo admite endpoints `127.0.0.1`; no cambia firewall, reloj del sistema,
servicios AGORA ni su base de datos. Las claves efímeras viven únicamente en un
directorio privado `/tmp/agora-chaos-TEST-*`, nunca dentro del repositorio.

Cada ejecución conserva `report.json`, génesis y configuraciones públicas,
logs y hashes por altura, incluso si falla. El código de salida distingue FAIL;
PARTIAL conserva escenarios UNSUPPORTED y no equivale a completar WS-04.

## Reproducción

Los auxiliares Go se compilan, sin red, contra el checkout oficial fijado por
`build_cometbft.py`, usando el Go y cachés ya preparados en este PC. Ejemplo:

```sh
cd /home/merari-acero/agora
.venv/bin/python native/tools/chaos_build_helpers.py \
  --cache /tmp/agora-native-build-20260909 \
  --output /tmp/agora-chaos-repro-helpers \
  --report audit/local-alpha-v02/chaos/helper-reproducibility.json
AGORA_ENV=test PYTHONPATH=native .venv/bin/python native/tools/chaos_network.py \
  --engine /tmp/agora-native-build-20260909/bin/cometbft \
  --signer /tmp/agora-chaos-repro-helpers/chaos-signer \
  --evidence-tool /tmp/agora-chaos-repro-helpers/chaos-evidence \
  --output-root audit/local-alpha-v02/chaos --lag-blocks 220
```

Los hashes de auxiliares también se validan: una recompilación distinta requiere
revisión explícita del artefacto antes de actualizar la lista aprobada.

## Interpretación

- Las particiones 3+1 y 2+2 cierran conexiones en proxies TCP dirigidos por arista.
- La latencia afecta segmentos leídos del stream; la pérdida cierra conexiones.
  No se presentan como pérdida ni reordenamiento de paquetes IP.
- `chaos_signer.go` usa la interfaz oficial remote signer. Altera el timestamp
  solicitado del voto ±60 s, retrasa firmas y rechaza propuestas explícitamente.
  Esto no cambia el reloj del proceso ni prueba todos los escenarios de clock skew.
- `chaos_abci.py` es un wrapper TEST declarado; puede proponer bytes inválidos
  o retener PrepareProposal para matar al productor durante esa solicitud.
  El código ABCI de producción no se parchea.
- `chaos_network_evidence.go` construye DuplicateVoteEvidence con un voto real
  comprometido y otro conflictivo firmado por la misma clave TEST; el harness
  comprueba aceptación RPC y presencia posterior en bloque. No afirma castigo.
- `chaos_double_sign.go` conserva además una caracterización offline independiente,
  que por sí sola no sustituye la detección en red.
- Los fallos se inyectan sobre un validador de cuatro. Dos desconectados prueban
  ausencia de quórum, no seguridad con dos validadores Byzantine.
- Cuatro procesos en este PC no son cuatro operadores o máquinas independientes.

## Pérdida y reordenamiento IP reales en namespace efímera

`--netem-only` exige namespaces de usuario y red distintas a las de PID 1 y UID
0 dentro de la namespace. Ejecuta `tc netem` únicamente en ese loopback, registra
paquetes realmente descartados y restaura la disciplina antes de salir. No debe
invocarse `tc` sobre la red anfitriona. Ejemplo desde la raíz del proyecto:

```sh
unshare --user --map-root-user --net sh -c '
  /usr/sbin/ip link set lo up &&
  exec env AGORA_ENV=test PYTHONPATH=native .venv/bin/python native/tools/chaos_network.py \
    --engine /tmp/agora-native-build-20260909/bin/cometbft \
    --output-root audit/local-alpha-v02/chaos --netem-only'
```

Los auxiliares se construyen con `-trimpath -buildvcs=false -ldflags=-buildid=`,
CGO desactivado y toolchain fijado; el builder compara dos directorios de fuentes
diferentes antes de declarar reproducibilidad. Los resultados anteriores conservan
los hashes de los binarios efectivamente usados, aunque sean anteriores a esa mejora.

Para la campaña de aceptación, añadir `--require-clean-source` después de guardar
el candidato en Git. El harness rechaza fuentes nativas modificadas o sin seguimiento,
archiva `HEAD:native` como `native-source.tar` y registra su SHA-256. Este archivo
contiene exclusivamente los archivos versionados bajo `native`; las claves efímeras
siguen fuera del repositorio y del archivo de fuentes.
