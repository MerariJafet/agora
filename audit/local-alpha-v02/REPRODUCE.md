# Reproducción local del candidato

Commit final: `aa21f2e6fac27362da1017ca5800a1ded1bdb7bf`. El árbol nativo coincide exactamente con la campaña congelada c37419e216ce181831546e0d251674de3f8e5d4b. Copiar o clonar el repositorio y hacer checkout de ese commit en un directorio separado. No modificar el checkout operativo del usuario.

```bash
python3 -m venv .venv
.venv/bin/pip install -r native/requirements.txt pytest==9.1.1 ruff==0.16.4
AGORA_ENV=test .venv/bin/pytest -c native/pyproject.toml --confcutdir=native native/tests -q
.venv/bin/ruff check native
.venv/bin/python native/tools/time_policy.py
PYTHONPATH=native .venv/bin/python native/tools/monetary_campaign.py --sequences 100000 --seed 20260909 --output /tmp/tokoin-money-NEW-RUN
```

La carpeta de salida debe ser nueva. La semilla reproduce el mismo corpus; cambiarla crea otra campaña. El corpus se genera con claves TEST derivables, nunca destinadas a fondos reales.

Motor y auxiliares:

```bash
.venv/bin/python native/tools/build_cometbft.py --cache /tmp/tokoin-build --report /tmp/tokoin-build.json
.venv/bin/python native/tools/chaos_build_helpers.py --cache /tmp/tokoin-build --output /tmp/tokoin-helpers --report /tmp/tokoin-helpers.json
AGORA_ENV=test PYTHONPATH=native .venv/bin/python native/tools/chaos_network.py --engine /tmp/tokoin-build/bin/cometbft --signer /tmp/tokoin-helpers/chaos-signer --evidence-tool /tmp/tokoin-helpers/chaos-evidence --output-root /tmp/tokoin-chaos-evidence --lag-blocks 220 --require-clean-source
```

El arnés puede devolver PARTIAL por escenarios explícitamente no soportados; no convertir ese resultado en PASS para CI. La pérdida IP/reordenamiento usa modo netem dentro de namespaces efímeros; comandos y restricciones exactas en `native/tools/chaos_README.md`. No ejecutar tc sobre la red global del host.

Ciencia/API: instalar las dependencias de desarrollo del repositorio y usar el wrapper aislado. No ejecutar pytest directamente contra una base viva.

```bash
scripts/run-isolated-tests.sh tests/integration/test_local_alpha_science.py -q
scripts/run-isolated-tests.sh tests/integration/test_local_alpha_science_migration.py -q
```

Los resultados generados documentan que los trabajadores son Python sintéticos. Las APIs de los agentes reales y sus credenciales no se fabrican ni se necesitan para estas fixtures.

Verificar paquete de resultados:

```bash
.venv/bin/python native/tools/evidence_pack.py --root /RUTA/EVIDENCIA --output /RUTA/EVIDENCIA/EVIDENCE_INDEX.json --verify
```

El hash del índice debe compararse por un canal confiable; modificar índice y archivos simultáneamente no puede detectarse sin esa referencia externa. El índice no está firmado por un auditor humano.
