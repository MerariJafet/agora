#!/usr/bin/env python3
"""Four real loopback CometBFT nodes, no economic tokens or AGORA DB access."""

import argparse
import base64
import datetime
import fcntl
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "native"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tokoin_native.core import (
    UNIT,
    VERSION,
    address,
    authorization_hash,
    canonical,
    digest,
    distribution,
    make_genesis,
    merkle,
    review_commitment,
)
from tokoin_native.wallet import public_key, transaction


def rpc(port, method, **params):
    url = f"http://127.0.0.1:{port}/{method}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=3) as response:
        value = json.load(response)
    if "error" in value:
        raise RuntimeError(value["error"])
    return value["result"]


def wait_for(fn, seconds=60):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        try:
            result = fn()
            if result:
                return result
        except (OSError, RuntimeError, KeyError) as error:
            last = error
        time.sleep(0.25)
    raise RuntimeError(f"wait timeout: {last}")


def configure(path, changes):
    section = ""
    lines = []
    for line in path.read_text().splitlines():
        if re.fullmatch(r"\[.*\]", line):
            section = line[1:-1]
        key = line.split("=", 1)[0].strip()
        if (section, key) in changes:
            line = key + " = " + changes[(section, key)]
        lines.append(line)
    path.write_text("\n".join(lines) + "\n")


def run(engine, output):
    lock_dir = Path.home() / ".cache/agora-native-network-test"
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_lock = open(lock_dir / "run.lock", "a")
    fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    home = Path(tempfile.mkdtemp(prefix="agora-native-network-TEST-"))
    os.chmod(home, 0o700)
    nodehome = home / "nodes"
    subprocess.run(
        [str(engine), "testnet", "--v", "4", "--o", str(nodehome)], check=True, capture_output=True
    )
    ids = [
        subprocess.check_output(
            [str(engine), "show-node-id", "--home", str(nodehome / f"node{i}")], text=True
        ).strip()
        for i in range(4)
    ]
    base = 28100
    ports = [base + i * 10 + 1 for i in range(4)]
    keys = [Ed25519PrivateKey.generate() for _ in range(5)]
    pubs = [public_key(k) for k in keys]
    addresses = [address(p) for p in pubs]
    registry = {
        pubs[i]: {
            "institution_id": f"TEST-{i}",
            "controller_group": f"TEST-owner-{i}",
            "payout_address": addresses[i],
            "label": "INSTITUTIONAL_VALIDATOR_TEST",
        }
        for i in (0, 1)
    }
    stamp = int(time.time())
    base_genesis = json.loads((nodehome / "node0/config/genesis.json").read_text())
    validators = sorted(
        [
            {"public_key": base64.b64decode(v["pub_key"]["value"]).hex(), "power": int(v["power"])}
            for v in base_genesis["validators"]
        ],
        key=lambda v: v["public_key"],
    )
    genesis = make_genesis("tokoin-test-local-network", registry, addresses[4], stamp, validators)
    genesis_path = home / "app-genesis.json"
    genesis_path.write_bytes(canonical(genesis))
    comet_genesis = base_genesis
    comet_genesis.update(
        chain_id=genesis["chain_id"],
        app_state=genesis,
        genesis_time=datetime.datetime.fromtimestamp(stamp, datetime.UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    )
    comet_genesis["consensus_params"]["block"]["max_bytes"] = "1000000"
    comet_genesis["consensus_params"]["evidence"]["max_bytes"] = "100000"
    apps, nodes, handles = {}, {}, []
    evidence = {
        "mode": "TEST_NON_RECOGNIZABLE",
        "independent_operators": False,
        "engine": str(engine),
        "runtime_directory": str(home),
        "checks": {},
        "comet_genesis_sha256": __import__("hashlib")
        .sha256(json.dumps(comet_genesis).encode())
        .hexdigest(),
    }
    env = dict(os.environ, PYTHONPATH=str(ROOT / "native"))

    def start_app(i):
        log = open(home / f"app-{i}.log", "ab")
        handles.append(log)
        apps[i] = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tokoin_native.abci_server",
                "--genesis",
                str(genesis_path),
                "--db",
                str(home / f"app-{i}.sqlite"),
                "--port",
                str(base + i * 10),
            ],
            env=env,
            stdout=log,
            stderr=log,
        )

    def start_node(i):
        log = open(home / f"node-{i}.log", "ab")
        handles.append(log)
        nodes[i] = subprocess.Popen(
            [str(engine), "start", "--home", str(nodehome / f"node{i}")], stdout=log, stderr=log
        )

    def stop_node(i):
        if nodes[i].poll() is None:
            nodes[i].terminate()
            nodes[i].wait(timeout=15)

    def height(i=0):
        return int(rpc(ports[i], "status")["sync_info"]["latest_block_height"])

    def state(i=0):
        q = rpc(ports[i], "abci_query", path='"/state"')["response"]
        assert q["code"] == 0, q
        return json.loads(base64.b64decode(q["value"]))

    def send(i, kind, payload, reject=False):
        s = state()
        tx = transaction(
            keys[i], genesis, s["nonces"].get(addresses[i], 0) + 1, kind, payload
        )
        response = rpc(ports[0], "broadcast_tx_commit", tx="0x" + canonical(tx).hex())
        code = response["check_tx"]["code"]
        if reject:
            assert code != 0, response
        else:
            assert code == 0 and response["tx_result"]["code"] == 0, response
        return response

    try:
        for i in range(4):
            path = nodehome / f"node{i}/config"
            (path / "genesis.json").write_text(json.dumps(comet_genesis))
            configure(
                path / "config.toml",
                {
                    ("", "proxy_app"): f'"tcp://127.0.0.1:{base + i * 10}"',
                    ("rpc", "laddr"): f'"tcp://127.0.0.1:{ports[i]}"',
                    ("p2p", "laddr"): f'"tcp://127.0.0.1:{base + i * 10 + 2}"',
                    ("p2p", "persistent_peers"): '"'
                    + ",".join(
                        f"{ids[j]}@127.0.0.1:{base + j * 10 + 2}" for j in range(4) if j != i
                    )
                    + '"',
                    ("p2p", "allow_duplicate_ip"): "true",
                    ("p2p", "pex"): "false",
                    ("consensus", "timeout_commit"): '"500ms"',
                    ("", "log_level"): '"error"',
                },
            )
            start_app(i)
        time.sleep(0.5)
        for i in range(4):
            start_node(i)
        wait_for(lambda: all(height(i) >= 3 for i in range(4)))
        evidence["checks"]["four_nodes_empty_blocks"] = True
        groups = {
            "proposer": {addresses[2]: 1},
            "solver": {addresses[2]: 1},
            "contributors": {addresses[2]: 3, addresses[3]: 1},
            "institutions": {addresses[0]: 1, addresses[1]: 1},
            "infra": {addresses[4]: 1},
        }
        allocation = distribution(UNIT, groups)
        body = {
            "reward_id": "TEST-network-reward-1",
            "research_id": "TEST-fixture-research-1",
            "candidate_version": 1,
            "protocol_version": VERSION,
            "genealogy_root": "a" * 64,
            "paper_hash": "b" * 64,
            "dataset_manifest_hash": "c" * 64,
            "code_manifest_hash": "d" * 64,
            "reward_total": UNIT,
            "groups": groups,
            "distribution_root": merkle([[k, v] for k, v in allocation.items()]),
            "participant_controllers": ["TEST-researcher"],
        }
        reward_hash = authorization_hash(body)
        for i in (0, 1):
            send(
                i,
                "review_commit",
                {
                    "reward_hash": reward_hash,
                    "commitment": review_commitment(reward_hash, "APPROVED", str(i) * 64),
                },
            )
        for i in (0, 1):
            send(
                i,
                "review_reveal",
                {"reward_hash": reward_hash, "verdict": "APPROVED", "salt": str(i) * 64},
            )
        send(2, "authorize", body)
        assert state()["created"] == UNIT
        evidence["checks"]["signed_blind_reviews_reward_locked"] = True
        send(2, "authorize", body, reject=True)
        send(2, "finalize", {"reward_id": body["reward_id"]}, reject=True)
        send(2, "transfer", {"to": addresses[3], "amount": 1}, reject=True)
        evidence["checks"]["replay_early_finality_locked_spend_rejected"] = True
        h = height()
        stop_node(3)
        wait_for(lambda: height() >= h + 3)
        evidence["checks"]["three_of_four_liveness"] = True
        stop_node(2)
        time.sleep(3)
        h = height()
        time.sleep(3)
        assert height() == h, "chain progressed without >2/3"
        evidence["checks"]["two_of_four_halts"] = True
        start_node(2)
        wait_for(lambda: height() >= h + 3)
        start_node(3)
        wait_for(lambda: height(3) >= h + 3)
        evidence["checks"]["quorum_recovery_lagging_node_sync"] = True
        stop_node(3)
        apps[3].terminate()
        apps[3].wait(timeout=15)
        start_app(3)
        time.sleep(0.5)
        start_node(3)
        target = height() + 2
        wait_for(lambda: height(3) >= target)
        evidence["checks"]["application_restart_replay"] = True
        common = min(height(i) for i in range(4)) - 1
        blocks = [rpc(p, "block", height=str(common)) for p in ports]
        assert len({b["block_id"]["hash"] for b in blocks}) == 1
        roots = []
        for i in range(4):
            con = sqlite3.connect(f"file:{home}/app-{i}.sqlite?mode=ro", uri=True)
            roots.append(
                con.execute("SELECT state_root FROM blocks WHERE height=?", (common,)).fetchone()[0]
            )
            con.close()
        assert len(set(roots)) == 1
        assert all(state(i)["created"] == UNIT for i in range(4))
        evidence["checks"]["same_block_and_state_roots_no_double_issuance"] = True
        evidence.update(
            common_height=common,
            block_hash=blocks[0]["block_id"]["hash"],
            state_root=roots[0],
            created_test_units=UNIT,
            genesis_sha256=digest("tokoin.genesis.v2", genesis),
            status="PASS",
        )
    except Exception as error:
        evidence.update(status="FAIL", error=str(error))
        raise
    finally:
        for proc in [*nodes.values(), *apps.values()]:
            if proc.poll() is None:
                proc.terminate()
        for proc in [*nodes.values(), *apps.values()]:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        for handle in handles:
            handle.close()
        evidence["all_spawned_processes_stopped"] = all(
            p.poll() is not None for p in [*nodes.values(), *apps.values()]
        )
        output.write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.engine, args.output)
