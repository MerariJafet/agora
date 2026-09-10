# EXTERNAL_OPERATOR_REHEARSAL — V0.3 preparation

Status: preparation for three external people on separate machines. No external operator has been contacted, enrolled or represented as having passed by this document. This is not a public testnet, mainnet or proof of decentralization.

## Prerequisites and release handoff

The release owner supplies an immutable source archive, `RELEASE_MANIFEST_V03.json`, the paper evidence index, native application genesis, CometBFT genesis, pinned engine binary/build report and an offline wheelhouse for `native/requirements.txt`. The operator obtains the release-manifest SHA-256 through a second authenticated channel. A manifest included in an archive cannot authenticate itself. Missing artifacts are a defect, not permission to improvise a different dependency or genesis.

Use a dedicated TEST VM or machine, Python compatible with the pinned dependencies, enough disk for the complete genesis-to-current chain, and a fresh user-owned node directory. Never use a pre-existing validator key, wallet or production service. The developer must not silently repair an operator machine; every correction gets an issue ID and a repeated step in the report.

The source supports loopback ABCI. RPC and ABCI stay on loopback. Private P2P connectivity between operators requires an agreed TEST VPN or SSH transport and peer addresses recorded in the genesis handoff. No public exposure is implied. Network admission and the validator set are fixed by the chosen TEST genesis; a node key is not an automatic right to join consensus.

## Verify the paper artifact index (offline)

Run from the directory containing `PAPER_EVIDENCE_INDEX.json`:

```bash
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
root = Path.cwd().resolve()
index = json.loads((root / 'PAPER_EVIDENCE_INDEX.json').read_text())
for item in index['files']:
    path = (root / item['path']).resolve()
    if root not in path.parents or not path.is_file():
        raise SystemExit('FAIL: path missing or outside artifact root')
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != item['sha256'] or path.stat().st_size != item['bytes']:
        raise SystemExit('FAIL: hash/size mismatch: ' + item['path'])
print('PASS: all indexed paper artifact bytes verified')
PY
```

This checks indexed files only, not unlisted files or the authenticity of the manifest. Compare the release source and engine with the separately authenticated manifest as well.

## Install and inspect without network access

Set `rehearsal_source`, `rehearsal_wheels`, `rehearsal_engine` and `rehearsal_node` to absolute paths for the received source, offline wheelhouse, verified CometBFT binary and a fresh node home. Preserve these values in the operator report without publishing private key paths beyond the local machine.

```bash
python3 -m venv "$rehearsal_source/.rehearsal-venv"
"$rehearsal_source/.rehearsal-venv/bin/pip" install --no-index \
  --find-links "$rehearsal_wheels" -r "$rehearsal_source/native/requirements.txt"
"$rehearsal_engine" version
PYTHONPATH="$rehearsal_source/native" \
  "$rehearsal_source/.rehearsal-venv/bin/python" \
  -m tokoin_native.abci_server --help
```

If wheel/platform compatibility fails, stop the installation and retain the complete error. The pinned build helper may separately reproduce the engine with `--offline` only when its verified source, toolchain archives and Go module cache are present. A development-machine cache is not proof of a fully distributable bundle.

## Generate an independent TEST validator identity

```bash
umask 077
"$rehearsal_engine" init --home "$rehearsal_node"
"$rehearsal_engine" show-validator --home "$rehearsal_node"
"$rehearsal_engine" show-node-id --home "$rehearsal_node"
```

Share only the displayed public validator key and node ID. Do not send `priv_validator_key.json`, node key files or wallet secrets. Keep `priv_validator_state.json` consistent with the consensus data; never reset signing state to force a restart. Never run two processes with the same signing key.

The coordinator constructs the common TEST genesis from independent public keys, without changing frozen monetary rules. Each operator verifies all public keys/powers and the genesis hashes before installing it in their fresh node. No coordinator-authored secret keys are distributed. The native `consensus_validators` set must match the CometBFT genesis validators exactly. Stop if the chain is not explicitly TEST or economic recognition is enabled.

## Start, verify and recover

After installing the agreed genesis and configuring private P2P peers, run the application in one terminal and CometBFT in another:

```bash
PYTHONPATH="$rehearsal_source/native" \
  "$rehearsal_source/.rehearsal-venv/bin/python" \
  -m tokoin_native.abci_server --genesis "$rehearsal_node/native-genesis.json" \
  --db "$rehearsal_node/native.sqlite" --port 26658
"$rehearsal_engine" start --home "$rehearsal_node" \
  --proxy_app tcp://127.0.0.1:26658 --rpc.laddr tcp://127.0.0.1:26657
```

Record exact commands, config hashes and complete logs. Synchronize from genesis: snapshot/state-sync acceptance is not currently claimed. Query `/status` and `/block?height=H` on loopback for a height H agreed by all operators. Compare the same canonical block and application state, accounting for CometBFT's header AppHash convention (a block header commits the previous application result). Comparing unrelated latest heights is invalid.

Stop both processes normally, preserve database and signing state, restart with the same verified genesis, and demonstrate progress without duplicate signing. Repeat a jointly scheduled partition using only the TEST transport; do not alter host-global firewall rules. With a four-validator equal-power genesis, record three-plus-one and two-plus-two partition behavior and recovery. Preserve failed/delayed observations. Operators report their own evidence rather than accepting a coordinator's latest RPC as proof.

An exported native application journal can be replayed offline with `native/tools/verify_export.py --expected-genesis-hash HASH EXPORT`. The hash must be independently trusted. This validates deterministic application replay, not CometBFT signatures; both are separate report fields.

## Reproducibility report template

```json
{
  "stage": "EXTERNAL_OPERATOR_REHEARSAL",
  "operator_pseudonym": "TO_BE_COMPLETED_BY_OPERATOR",
  "independent_of_development_pc_administration": null,
  "machine_os_architecture": null,
  "source_commit": null,
  "release_manifest_sha256": null,
  "engine_sha256": null,
  "genesis_hash": null,
  "own_validator_public_key": null,
  "installation": "UNKNOWN",
  "genesis_sync": "UNKNOWN",
  "restart_recovery": "UNKNOWN",
  "controlled_partition_recovery": "UNKNOWN",
  "canonical_height": null,
  "block_hash": null,
  "apphash": null,
  "application_replay": "UNKNOWN",
  "consensus_signature_verification": "UNKNOWN",
  "documentation_defects": [],
  "developer_interventions": [],
  "evidence_files_and_hashes": [],
  "operator_attestation": null
}
```

Acceptance requires three real independently administered installations and independently generated validator keys, complete reports and disclosed interventions. A local dry run can validate command syntax and packaging; it cannot complete that external acceptance criterion.

## Prepared local handoff artifact

The developer prepared `audit/v03/operator-bundle/source.tar`, the pinned `cometbft` executable, an offline Python wheelhouse and `installation-results-002.json`. That result records a fresh local virtual environment installing with `--no-index`, node initialization with a new private TEST key, CLI inspection and replay of a public native journal against an explicit trusted genesis hash. The first installation attempt is retained in `installation-results.json`: its replay command omitted the mandatory expected-genesis argument and failed closed. The corrected run supplied it and passed. This is a local installation rehearsal, not an external person's report.

The wheelhouse is for the tested Linux x86_64 / Python 3.12 environment. Other platforms must reproduce a documented compatible bundle; compatibility is not assumed. The final release manifest binds artifact hashes. This artifact enables offline installation and recorded-journal replay now. Joining a new multi-owner validator set still requires the actual operators' public keys, agreed private-network addresses, jointly verified genesis and reports. No operational external-network genesis or admission has been fabricated.
