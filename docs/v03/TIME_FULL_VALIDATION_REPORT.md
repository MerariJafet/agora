# V0.3 — validación de reloj completo en máquinas virtuales

Estado: **TIME_COMPLETE como caracterización local de seguridad y recuperación**, con disponibilidad degradada documentada en los relojes negativos extremos. No significa tolerancia ilimitada ni disponibilidad de cuatro nodos bajo cualquier desfase.

## Alcance y método

Se ejecutan cuatro kernels Linux independientes bajo KVM, cada uno con CometBFT 0.38.26 y ABCI Python dentro de la VM. El reloj modificado es `CLOCK_REALTIME` del kernel invitado mediante `clock_settime`, no una firma con timestamp artificial. No se cambia el reloj del host. El supervisor de laboratorio es PID 1; no existe daemon NTP en los invitados. Las VMs usan 768 MiB y un vCPU cada una. No hay operadores ni máquinas físicas independientes.

CometBFT conserva el SHA-256 `6edb2aa0f223e71758a48cf3d13d9d7ffd26f3357585bebe54311ba71f11ac3f`. Se utiliza el kernel instalado 7.0.0-31-generic y se registra su hash. La lectura privilegiada se limita al kernel instalado; la construcción y ejecución de QEMU se realizan como usuario. No se instala un sistema operativo descargado ni se modifica la red del host.

Cada VM tiene red QEMU user-mode y puerto de control/RPC/P2P publicado únicamente en loopback del host. El invitado carece de ruta por defecto. Proxies TCP entre pares ejecutan particiones reales de conexiones, sin firewall/TAP. Los reinicios son del proceso validador y del ABCI dentro de la VM; no se afirma haber probado reinicio eléctrico de una VM con disco persistente. Las claves efímeras TEST permanecen en un directorio temporal 0700 y no se incluyen en evidencias públicas.

## Criterios de aceptación y límites

En los perfiles 0, +60, -60, +300, -300, +1800 y -1800 segundos se desfasa un validador de cuatro. Se comprueba que los tres correctos conservan quorum, no hay raíces distintas a una altura común y un reward LOCKED no madura prematuramente. Se registran por separado disponibilidad del validador desfasado y seguridad de la red. Un nodo excluido por tolerancia temporal no equivale a cuatro validadores sanos.

Después de los perfiles, todos los relojes invitados se adelantan expresamente 365 días para ensayar el camino FINALIZED en tiempo consensuado. Esto es una simulación temporal real dentro de kernels invitados; no demuestra el transcurso de un año calendario. Un posterior retroceso de un reloj comprueba que los balances finalizados no se vuelven a bloquear. La seguridad de tiempo consensuado presupone el modelo BFT: no se demuestra resistencia a una mayoría de validadores que manipule sus relojes conjuntamente.

## Fallos preservados

- `audit/v03/time/run-001`: perfiles 0/+60/-60/+300 completados; falla de timeout con -300. El arranque de un nodo cuyo reloj antecede al génesis muestra `Genesis time is in the future. Sleeping until then`. Se ajustó el génesis del laboratorio a una hora anterior a los perfiles. No se cambió el motor.
- `audit/v03/time/run-002`: el nodo con -300 segundos rechaza un bloque honesto porque supera la tolerancia de un minuto y registra `CONSENSUS FAILURE!!!`; su rutina de consenso se detiene mientras los tres correctos siguen produciendo bloques. Se conserva log completo y stack trace. Este es un fallo operativo real de disponibilidad del nodo desfasado, no divergencia ABCI.
- `audit/v03/time/run-003`: el reinicio con reloj todavía atrasado también puede abortar durante replay y dejar RPC inaccesible. Se conserva el fallo de conexión del harness y el stack trace del motor. La campaña siguiente registra esta indisponibilidad antes de corregir el reloj, sin tratarla como disponibilidad sana.
- La aceptación posterior separa seguridad del quorum y disponibilidad del nodo; exige registrar la exclusión y probar recuperación corrigiendo solamente el reloj invitado y reiniciando. Cambiar el criterio de caracterización no elimina los fallos anteriores ni constituye corrección de CometBFT.

## Reproducción local

```bash
cd "$AGORA_REPO"
AGORA_ENV=test .venv/bin/python native/tools/v03_vm_time.py --output audit/v03/time/NEW_UNIQUE_RUN
.venv/bin/python native/tools/v03_vm_verify.py audit/v03/time/NEW_UNIQUE_RUN
.venv/bin/python native/tools/v03_vm_replay.py audit/v03/time/NEW_UNIQUE_RUN
AGORA_ENV=test .venv/bin/pytest -c native/pyproject.toml --confcutdir=native native/tests/test_v03_vm_evidence.py -q
```

Requisitos reales: `/dev/kvm` con acceso lectura/escritura, QEMU, busybox estático, cpio, zstd, kernel instalado y módulo e1000 correspondiente, Python 3.12 y dependencias nativas ya verificadas. El harness rechaza un binario CometBFT con hash distinto. La ruta y versión del kernel están declaradas en el código; no es un instalador portable universal.

## Operación

Un desfase negativo importante debe tratarse como incidente de disponibilidad: restaurar una fuente horaria confiable del operador, verificar el desfase y reiniciar el nodo, conservando sus claves y datos. No aumentar silenciosamente la tolerancia de consenso, cambiar el génesis ni borrar WAL para ocultar el incidente. Este laboratorio no entrega todavía un servicio automático de sincronización o monitor temporal para operadores externos.

## Resultados finales generados desde run-004/results.json

| Desfase solicitado (s) | Desfase observado (s) | Nodo desfasado | Seguridad/quorum y recuperación | Altura común | Finalización prematura |
|---:|---:|---|---|---:|---|
| +0 | -0.002 | Participa | PASS | 20 | Rechazada |
| +60 | +59.998 | Participa | PASS | 32 | Rechazada |
| -60 | -60.002 | Participa | PASS | 45 | Rechazada |
| +300 | +299.998 | Participa | PASS | 57 | Rechazada |
| -300 | -300.002 | Excluido; corrección de reloj + reinicio | PASS | 68 | Rechazada |
| +1800 | +1799.998 | Participa | PASS | 81 | Rechazada |
| -1800 | -1800.002 | Excluido; corrección de reloj + reinicio | PASS | 92 | Rechazada |

Se compararon **104 alturas**, con cuatro AppHash y cuatro hashes de bloque por altura. No se observó divergencia. Los cuatro exports se reconstruyeron en procesos nuevos usando exactamente la fuente archivada; llegaron a altura **105**, raíz `8ebf476b16be971f0b3de2bc68689df1a9c483c7213978ed7069fe6bf2792365`. El replay aplica transiciones nativas; no es un light client ni verifica por sí solo las firmas BFT.

La recompensa del ensayo es **1 TOKOIN TEST sin reconocimiento económico**, originada mediante commit/reveal, autorización firmada y broadcast a la red. Es un fixture monetario explícito, no una investigación científica ni validación institucional. Este ensayo usa el génesis compatible de tiempo; el ciclo científico V0.3 se evalúa por separado.

La partición 2+2 detuvo las cuatro alturas en `[102, 102, 102, 102]` y se recuperó al restablecer conexiones. El salto posterior de 365 días es una simulación de relojes de VMs y permite ensayar finalización; el retroceso de un reloj no cambia los balances ya finalizados.

Duración registrada del host: 171.342 segundos de reloj civil frente a 171.342 segundos monotónicos (diferencia -0.000000 s). El supervisor exige PID 1 y un marcador TEST del kernel para impedir su ejecución en el host.

Verificación auxiliar: **11 pruebas PASS** del verificador, incluyendo rechazo de perfiles faltantes, clock ficticio, divergencia, corrupción de archivo fuente, altura faltante, reinicio no demostrado, aceptación prematura y salto del reloj host. Ruff: PASS en los archivos del trabajo temporal.

## Índice de evidencia

- `audit/v03/time/run-004/results.json`: resultados y tiempos reales.
- `apphash-matrix.json`: todas las comparaciones de alturas.
- `transactions.json`: transacciones firmadas, respuestas y rechazos esperados.
- `node-*-application-export.json` y `replay-results.json`: replay desde génesis.
- `genesis.json` y `node-*-config.toml`: configuración pública.
- `vm-*-node.log`, `vm-*-app.log`, `vm-*-serial.log`, `profile-*-faulty-node.log`: logs completos y fallos.
- `application-source.tar.gz`, `runtime-input-hashes.json`: código y hashes exactos de insumos de ejecución.
- `verification.json`: verificación automática.
- `audit/v03/time/vm-evidence-tests.xml`: pruebas auxiliares.

No se cambió CometBFT, no se modificó la política monetaria y no se efectuó ningún lanzamiento económico. Las VMs se detuvieron al terminar. Los nodos en distintos kernels del mismo PC no son operadores independientes.
