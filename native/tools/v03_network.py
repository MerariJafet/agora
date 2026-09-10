#!/usr/bin/env python3
"""Reusable four-node native TEST transport; frozen application source, real CometBFT.

No direct state mutations. Genesis factory receives independently generated TEST
consensus public keys. Private validator keys stay in the mode-0700 runtime only.
"""

import argparse
import base64
import datetime
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "native"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_network_test import configure, rpc, wait_for

from tokoin_native.core import canonical, digest

ENGINE = Path("/tmp/agora-native-build-20260909/bin/cometbft")  # noqa: S108 - hash verified
ENGINE_SHA256 = "6edb2aa0f223e71758a48cf3d13d9d7ffd26f3357585bebe54311ba71f11ac3f"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class NativeNetwork:
    """Use `with NativeNetwork(output, genesis_factory=...) as network`.

    `genesis_factory(validators, timestamp)` must return a complete TEST genesis.
    Alternatively `genesis` accepts a template with empty consensus_validators;
    generated public validators and current TEST genesis time replace those fields.
    Always sign against `network.genesis`, never the preconstruction template.
    """

    def __init__(self, output, genesis=None, *, genesis_factory=None, engine=ENGINE):
        self.output, self.engine = Path(output).resolve(), Path(engine).resolve()
        if self.output.exists() and any(self.output.iterdir()):
            raise FileExistsError("Network evidence directory must be fresh")
        if sha(self.engine) != ENGINE_SHA256:
            raise ValueError("Unverified CometBFT binary")
        if (genesis is None) == (genesis_factory is None):
            raise ValueError("Exactly one genesis template or factory required")
        self.output.mkdir(parents=True, exist_ok=True)
        self.home = Path(tempfile.mkdtemp(prefix="agora-v03-network-TEST-"))
        os.chmod(self.home, 0o700)
        self.processes, self.handles = [], []
        self.closed = False
        self.ports = []
        while len(self.ports) < 12:
            candidate = port()
            if candidate not in self.ports:
                self.ports.append(candidate)
        self.app_ports, self.rpc_ports, self.peer_ports = (
            self.ports[:4],
            self.ports[4:8],
            self.ports[8:12],
        )
        self.report = {
            "schema_version": "AGORA_V03_RUN_V1",
            "run_id": self.output.name,
            "status": "RUNNING",
            "engine_sha256": ENGINE_SHA256,
            "runner_sha256": sha(Path(__file__)),
            "transport_helper_sha256": sha(Path(__file__).with_name("run_network_test.py")),
            "independent_operators": False,
            "mode": "TEST_NON_RECOGNIZABLE",
            "consensus_results": [],
            "apphash_consistency": [],
            "transactions": [],
            "replays": [],
            "errors": [],
            "limitations": [
                {
                    "status": "LIMITATION",
                    "reason": "One PC, four processes; not external decentralization",
                },
                {
                    "status": "LIMITATION",
                    "reason": "Application replay alone does not verify BFT signatures",
                },
            ],
        }
        try:
            self._prepare(genesis, genesis_factory)
        except Exception as error:
            self.report["errors"].append(repr(error))
            self.close()
            raise

    def _prepare(self, template, factory):
        source = ROOT / "native/tokoin_native"
        before = {str(p.relative_to(source)): sha(p) for p in source.rglob("*.py")}
        self.snapshot = self.home / "source/native"
        shutil.copytree(
            source,
            self.snapshot / "tokoin_native",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        (self.snapshot / "tools").mkdir()
        shutil.copy2(
            ROOT / "native/tools/verify_export.py", self.snapshot / "tools/verify_export.py"
        )
        after = {str(p.relative_to(source)): sha(p) for p in source.rglob("*.py")}
        copied = {
            str(p.relative_to(self.snapshot / "tokoin_native")): sha(p)
            for p in (self.snapshot / "tokoin_native").rglob("*.py")
        }
        if before != after or before != copied:
            raise RuntimeError(
                "Application source changed during snapshot; rerun with stable source"
            )
        self.report["source_hashes"] = before
        self.report["source_commit"] = subprocess.check_output(
            [shutil.which("git") or "/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        self.report["snapshot_is_dirty_tree"] = True
        with tarfile.open(self.output / "application-source.tar.gz", "w:gz") as archive:
            archive.add(self.snapshot, arcname="native")
        self.report["source_archive_sha256"] = sha(self.output / "application-source.tar.gz")
        self.env = dict(os.environ, PYTHONPATH=str(self.snapshot), AGORA_ENV="test")
        self.nodes_home = self.home / "nodes"
        subprocess.run(
            [str(self.engine), "testnet", "--v", "4", "--o", str(self.nodes_home)],
            check=True,
            capture_output=True,
        )
        self.node_ids = [
            subprocess.check_output(
                [str(self.engine), "show-node-id", "--home", str(self.nodes_home / f"node{i}")],
                text=True,
            ).strip()
            for i in range(4)
        ]
        comet = json.loads((self.nodes_home / "node0/config/genesis.json").read_text())
        validators = sorted(
            [
                {
                    "public_key": base64.b64decode(v["pub_key"]["value"]).hex(),
                    "power": int(v["power"]),
                }
                for v in comet["validators"]
            ],
            key=lambda v: v["public_key"],
        )
        stamp = int(time.time()) - 2
        if factory is not None:
            self.genesis = factory(validators, stamp)
        else:
            if template.get("consensus_validators"):
                raise ValueError("Template must have empty consensus_validators; use factory")
            self.genesis = dict(template, consensus_validators=validators, timestamp=stamp)
        if (
            not self.genesis["chain_id"].startswith("tokoin-test-")
            or self.genesis["mode"] != "TEST_NON_RECOGNIZABLE"
            or self.genesis["consensus_validators"] != validators
        ):
            raise ValueError("TEST genesis / consensus set mismatch")
        self.genesis_path = self.home / "native-genesis.json"
        self.genesis_path.write_bytes(canonical(self.genesis))
        shutil.copy2(self.genesis_path, self.output / "native-genesis.json")
        comet.update(
            chain_id=self.genesis["chain_id"],
            app_state=self.genesis,
            genesis_time=datetime.datetime.fromtimestamp(stamp, datetime.UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        )
        comet["consensus_params"]["block"]["max_bytes"] = "1000000"
        comet["consensus_params"]["evidence"]["max_bytes"] = "100000"
        (self.output / "comet-genesis.json").write_text(
            json.dumps(comet, sort_keys=True, indent=2) + "\n"
        )
        self.report["genesis_hash"] = digest("tokoin.genesis.v2", self.genesis)
        for i in range(4):
            config = self.nodes_home / f"node{i}/config"
            (config / "genesis.json").write_text(json.dumps(comet))
            configure(
                config / "config.toml",
                {
                    ("", "proxy_app"): f'"tcp://127.0.0.1:{self.app_ports[i]}"',
                    ("rpc", "laddr"): f'"tcp://127.0.0.1:{self.rpc_ports[i]}"',
                    ("p2p", "laddr"): f'"tcp://127.0.0.1:{self.peer_ports[i]}"',
                    ("p2p", "persistent_peers"): '"'
                    + ",".join(
                        f"{self.node_ids[j]}@127.0.0.1:{self.peer_ports[j]}"
                        for j in range(4)
                        if j != i
                    )
                    + '"',
                    ("p2p", "allow_duplicate_ip"): "true",
                    ("p2p", "pex"): "false",
                    ("consensus", "timeout_commit"): '"300ms"',
                    ("", "log_level"): '"error"',
                },
            )
            shutil.copy2(config / "config.toml", self.output / f"node-{i}-config.toml")

    def _spawn(self, name, args, env=None):
        handle = (self.output / f"{name}.log").open("ab")
        self.handles.append(handle)
        proc = subprocess.Popen(args, cwd=self.home, env=env, stdout=handle, stderr=handle)
        self.processes.append(proc)
        return proc

    def __enter__(self):
        try:
            for i in range(4):
                self._spawn(
                    f"app-{i}",
                    [
                        sys.executable,
                        "-m",
                        "tokoin_native.abci_server",
                        "--genesis",
                        str(self.genesis_path),
                        "--db",
                        str(self.home / f"app-{i}.sqlite"),
                        "--port",
                        str(self.app_ports[i]),
                    ],
                    self.env,
                )
            time.sleep(0.5)
            for i in range(4):
                self._spawn(
                    f"node-{i}",
                    [str(self.engine), "start", "--home", str(self.nodes_home / f"node{i}")],
                )
            wait_for(lambda: all(self.height(i) >= 3 for i in range(4)), seconds=45)
            self.report["consensus_results"].append(
                {
                    "scenario": "four_nodes_start",
                    "status": "PASS",
                    "evidence": ["node-0.log", "node-1.log", "node-2.log", "node-3.log"],
                }
            )
            return self
        except Exception as error:
            self.report["errors"].append(repr(error))
            self.close()
            raise

    def height(self, node=0):
        return int(rpc(self.rpc_ports[node], "status")["sync_info"]["latest_block_height"])

    def state(self, node=0):
        value = rpc(self.rpc_ports[node], "abci_query", path='"/state"')["response"]
        if value.get("code", 0) != 0:
            raise RuntimeError(value)
        return json.loads(base64.b64decode(value["value"]))

    def submit(self, signed_tx, expect_reject=False):
        raw = canonical(signed_tx)
        tx_hash = hashlib.sha256(raw).hexdigest().upper()
        record = {
            "index": len(self.report["transactions"]),
            "transaction": signed_tx,
            "tx_hash": tx_hash,
            "expect_reject": expect_reject,
            "status": "SUBMITTED",
        }
        self.report["transactions"].append(record)
        self._write_transactions()
        try:
            try:
                response = rpc(self.rpc_ports[0], "broadcast_tx_commit", tx="0x" + raw.hex())
            except urllib.error.HTTPError as error:
                body = error.read(8192).decode("utf-8", errors="replace")
                record["broadcast_http_error"] = {"status": error.code, "body": body}
                known_inclusion = any(
                    item.get("tx_hash") == tx_hash and item.get("status") == "INCLUDED"
                    for item in self.report["transactions"][:-1]
                )
                if expect_reject and known_inclusion and "tx already exists in cache" in body:
                    record.update(
                        status="EXPECTED_REJECTION", rejection_layer="CometBFT mempool cache"
                    )
                    return record
                raise
            record["broadcast_response"] = response
            if expect_reject:
                if response["check_tx"]["code"] == 0:
                    raise AssertionError("Expected CheckTx rejection; received acceptance")
                record["status"] = "EXPECTED_REJECTION"
                record["rejection_layer"] = "ABCI CheckTx"
            else:
                if response["check_tx"]["code"] != 0 or response["tx_result"]["code"] != 0:
                    raise AssertionError(response)
                record["index_lookup_attempts"] = []

                def lookup():
                    try:
                        return rpc(self.rpc_ports[0], "tx", hash="0x" + tx_hash, prove="true")
                    except urllib.error.HTTPError as error:
                        record["index_lookup_attempts"].append(
                            {
                                "http_status": error.code,
                                "body": error.read(8192).decode("utf-8", errors="replace"),
                            }
                        )
                        return False

                # CometBFT indexes committed transactions asynchronously. Retry reads only;
                # never rebroadcast a transaction after uncertain inclusion.
                inclusion = wait_for(lookup, seconds=15)
                h = int(inclusion["height"])
                block = rpc(self.rpc_ports[0], "block", height=str(h))
                if base64.b64decode(inclusion["tx"]) != raw:
                    raise AssertionError("Inclusion bytes mismatch")
                txs = block["block"]["data"]["txs"] or []
                if raw not in [base64.b64decode(item) for item in txs]:
                    raise AssertionError("Signed transaction missing from canonical block")
                if inclusion["hash"] != tx_hash or response["hash"] != tx_hash:
                    raise AssertionError("Transaction hash mismatch")
                record.update(status="INCLUDED", height=h, inclusion=inclusion, block=block)
            return record
        except Exception as error:
            record.update(status="FAIL", error=repr(error))
            self.report["errors"].append(repr(error))
            raise
        finally:
            self._write_transactions()

    def _write_transactions(self):
        (self.output / "transactions.json").write_text(
            json.dumps(self.report["transactions"], sort_keys=True, indent=2) + "\n"
        )

    def compare(self):
        target = max(self.height(i) for i in range(4)) + 1
        wait_for(lambda: all(self.height(i) >= target for i in range(4)), seconds=30)
        height = min(self.height(i) for i in range(4)) - 1
        rows = []
        for i in range(4):
            block = rpc(self.rpc_ports[i], "block", height=str(height))
            next_block = rpc(self.rpc_ports[i], "block", height=str(height + 1))
            con = sqlite3.connect((self.home / f"app-{i}.sqlite").as_uri() + "?mode=ro", uri=True)
            try:
                root = con.execute(
                    "SELECT state_root FROM blocks WHERE height=?", (height,)
                ).fetchone()[0]
            finally:
                con.close()
            header_root = next_block["block"]["header"]["app_hash"].lower()
            if root != header_root:
                raise AssertionError("Journal AppHash does not match next CometBFT header")
            rows.append(
                {
                    "height": height,
                    "node_id": i,
                    "block_hash": block["block_id"]["hash"],
                    "apphash": root,
                    "header_commitment_height": height + 1,
                    "status": "PASS",
                }
            )
        if len({(r["block_hash"], r["apphash"]) for r in rows}) != 1:
            raise AssertionError("Honest node canonical AppHash divergence")
        self.report["apphash_consistency"].extend(rows)
        (self.output / "apphash-comparisons.json").write_text(
            json.dumps(self.report["apphash_consistency"], indent=2) + "\n"
        )
        return rows

    def close(self):
        if self.closed:
            return
        self.closed = True
        for proc in reversed(self.processes):
            if proc.poll() is None:
                proc.terminate()
        for proc in self.processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for handle in self.handles:
            handle.close()
        self.report["all_spawned_processes_stopped"] = all(
            p.poll() is not None for p in self.processes
        )
        for i in range(4):
            db = self.home / f"app-{i}.sqlite"
            if not db.exists() or not hasattr(self, "genesis"):
                continue
            export = self.output / f"node-{i}-application-export.json"
            try:
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "tokoin_native",
                        "export",
                        "--genesis",
                        str(self.genesis_path),
                        "--db",
                        str(db),
                        "--output",
                        str(export),
                    ],
                    env=self.env,
                    cwd=self.home,
                    check=True,
                    capture_output=True,
                    timeout=60,
                )
                replay = subprocess.run(
                    [
                        sys.executable,
                        str(self.snapshot / "tools/verify_export.py"),
                        str(export),
                        "--expected-genesis-hash",
                        self.report["genesis_hash"],
                    ],
                    env=self.env,
                    cwd=self.home,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.report["replays"].append(
                    {
                        "node_id": i,
                        "status": "PASS",
                        "export_sha256": sha(export),
                        "result": json.loads(replay.stdout),
                    }
                )
            except Exception as error:
                self.report["errors"].append(f"replay node {i}: {error!r}")
        self.report["status"] = (
            "PASS" if not self.report["errors"] and len(self.report["replays"]) == 4 else "FAIL"
        )
        self.report["private_key_exported"] = False
        (self.output / "results.json").write_text(
            json.dumps(self.report, sort_keys=True, indent=2) + "\n"
        )

    def __exit__(self, exc_type, exc, traceback):
        if exc is not None:
            self.report["errors"].append(repr(exc))
        else:
            try:
                self.compare()
            except Exception as error:
                self.report["errors"].append(repr(error))
                self.close()
                raise
        self.close()
        if exc is None and self.report["status"] != "PASS":
            raise RuntimeError(self.report["errors"])
        return False


def main():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from tokoin_native.core import address, make_genesis
    from tokoin_native.wallet import public_key, transaction

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    keys = [Ed25519PrivateKey.generate() for _ in range(3)]
    pubs = [public_key(k) for k in keys]
    registry = {
        pubs[i]: {
            "institution_id": f"TEST-{i}",
            "controller_group": f"TEST-owner-{i}",
            "payout_address": address(pubs[i]),
            "label": "INSTITUTIONAL_VALIDATOR_TEST",
        }
        for i in (0, 1)
    }
    with NativeNetwork(
        args.output,
        genesis_factory=lambda v, t: make_genesis(
            "tokoin-test-v03-transport-smoke", registry, address(pubs[2]), t, v
        ),
    ) as net:
        tx = transaction(
            keys[0],
            net.genesis,
            1,
            "review_commit",
            {"reward_hash": "a" * 64, "commitment": "b" * 64},
        )
        net.submit(tx)
        net.submit(tx, expect_reject=True)
        forged = transaction(
            keys[0],
            net.genesis,
            2,
            "review_commit",
            {"reward_hash": "c" * 64, "commitment": "d" * 64},
        )
        forged["signature"] = "0" * 128
        net.submit(forged, expect_reject=True)
    print(
        json.dumps(
            {
                "status": net.report["status"],
                "replays": len(net.report["replays"]),
                "transactions": len(net.report["transactions"]),
            }
        )
    )


if __name__ == "__main__":
    main()
