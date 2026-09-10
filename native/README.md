# TOKOIN native TEST implementation

Independent CometBFT 0.38.26 consensus engine + deterministic Python ABCI2 application.
No Ethereum/Base connection, no AGORA database balance authority, no premined treasury.
This is a working local technical prototype, **not a completed public/economic product**.
Only `TEST_NON_RECOGNIZABLE` genesis is accepted. Mainnet import is intentionally absent.

## Reproduce

From the AGORA repository, using Python3.12:

```bash
python -m venv .venv-native
.venv-native/bin/pip install -r native/requirements.txt pytest
AGORA_ENV=test .venv-native/bin/pytest -c native/pyproject.toml --confcutdir=native native/tests -q
python native/tools/build_cometbft.py --cache /tmp/agora-native-build-20260909
PYTHONPATH=native .venv-native/bin/python native/tools/run_network_test.py \
  --engine /tmp/agora-native-build-20260909/bin/cometbft \
  --output audit/native-2026-09-09/network-test.json
```

The build verifies pinned official Go/source SHA256 and Go module sums. Downloads and binaries
remain outside the repository. Official protobuf sources are vendored as generated namespaced
Python bindings with licenses, provenance and type stubs. Regeneration needs the five wheels
pinned with hashes in `tools/proto-tools.lock`, installed in an isolated venv, then
`generate_abci_bindings.py --cache <same cache>`. No global toolchain installation is required.

The network harness creates four real engines and four independent local application journals,
uses only loopback ports28100–28132, creates ephemeral TEST consensus keys outside the repo,
retains logs/history under its reported private temporary directory, and stops its processes
in `finally`. It serializes its own invocations. Do not share that runtime directory: it includes
TEST consensus private keys. Ordinary monetary signing keys are kept only in memory by the test.
No coins from this run have economic recognition.

## Inspection

Replace paths with the runtime directory recorded by the harness:

```bash
PYTHONPATH=native .venv-native/bin/python -m tokoin_native status \
  --genesis /runtime/app-genesis.json --db /runtime/app-0.sqlite
PYTHONPATH=native .venv-native/bin/python -m tokoin_native explorer \
  --genesis /runtime/app-genesis.json --db /runtime/app-0.sqlite --output /tmp/explorer.html
PYTHONPATH=native .venv-native/bin/python -m tokoin_native manifest \
  --genesis /runtime/app-genesis.json --db /runtime/app-0.sqlite --output /tmp/manifest-TEST.json
```

The inspector reads a consistent SQLite backup through a read-only source connection, then
replays it in an isolated copy. The explorer is an offline snapshot with balances, locked
rewards, research links, commitments and signed transaction history. It is not the existing
AGORA web wallet. Query paths `/state`, `/manifest`, `/explorer` are also available through
CometBFT ABCI query; proof requests and unauthenticated state snapshots are rejected.

`tools/prepare_agora_reward.py` reuses AGORA's existing public package integrity verifier,
checks a caller-supplied trusted candidate hash and hashes three actual artifact files. It
only creates a draft requiring blind institutional review, never a signature or broadcast.
The test fixture reuses an existing public synthetic AGORA export, explicitly TEST-only.

## Boundaries

- Block time comes from CometBFT, not Python's clock. Unit tests simulate365days; the real network
  test asserts that early finalization and spending locked funds are rejected.
- Journal replay verifies application transitions. It does not verify consensus signatures by
  itself. A complete verifier must anchor the full CometBFT genesis and validate signed commits.
- Four local processes are not four independent operators or machines.
- Two TEST reviewers and declared controller groups do not prove real institutions/independence.
- Institutional admission/censorship, scoring anti-abuse, operator funding, economic genesis,
  governance, external audits and complete AGORA UI integration remain open.
- Existing SQL/EVM history and balances are preserved and not auto-converted.

See `docs/native/CURRENT_STATE_AND_GAP_ANALYSIS.md` and the phase matrix in
`docs/native/TOKOIN_MAINNET_READINESS_CHECKLIST.md` for precise implementation scope.
