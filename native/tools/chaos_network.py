#!/usr/bin/env python3
"""Real local four-node fault harness; every run preserves public evidence and logs."""

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import resource
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from chaos_proxy import ProxyMesh, require_loopback
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from run_network_test import ROOT, configure, rpc, wait_for

from tokoin_native.core import MODE, address, canonical, make_genesis
from tokoin_native.wallet import public_key, transaction

ENGINE_SHA256 = "6edb2aa0f223e71758a48cf3d13d9d7ffd26f3357585bebe54311ba71f11ac3f"


def guard(engine, genesis, endpoints):
    if hashlib.sha256(engine.read_bytes()).hexdigest() != ENGINE_SHA256:
        raise ValueError("Unreviewed engine binary")
    if genesis.get("mode") != MODE or not genesis.get("chain_id", "").startswith("tokoin-test-"):
        raise ValueError("TEST genesis required")
    for endpoint in endpoints:
        require_loopback(endpoint)


def choose_base():
    for base in range(32000, 49000, 100):
        held = []
        try:
            for offset in list(range(46)) + list(range(50, 66)):
                s = socket.socket()
                held.append(s)
                s.bind(("127.0.0.1", base + offset))
            return base
        except OSError:
            pass
        finally:
            for s in held:
                s.close()
    raise RuntimeError("No free loopback test port range")


def run(
    engine,
    evidence_root,
    lag,
    signer=None,
    evidence_tool=None,
    netem_only=False,
    require_clean_source=False,
):
    started_monotonic = time.monotonic()
    run_id = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    output = evidence_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    home = Path(tempfile.mkdtemp(prefix="agora-chaos-TEST-"))
    os.chmod(home, 0o700)
    nodes_home = home / "nodes"
    report = {
        "run_id": run_id,
        "mode": MODE,
        "independent_operators": False,
        "private_runtime": str(home),
        "scenarios": {},
        "required_BFT_ids": [f"BFT-{i:03d}" for i in range(1, 16)],
        "status": "RUNNING",
        "limits": [
            "One host, four processes: not independent operators",
            "TCP stream delay/closure is not IP packet loss or reordering",
            "No claim of safety with >=1/3 Byzantine voting power",
        ],
    }
    nodes, apps, logs, mesh = {}, {}, [], None
    auxiliaries = []

    def persist():
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def check(name, fn):
        before = time.monotonic()
        try:
            detail = fn()
            report["scenarios"][name] = {
                "status": "PASS",
                "seconds": time.monotonic() - before,
                "evidence": detail,
            }
        except Exception as exc:
            report["scenarios"][name] = {"status": "FAIL", "error": str(exc)}
            persist()
            raise
        persist()

    try:
        if netem_only:
            uid_map = Path("/proc/self/uid_map").read_text().split()
            if len(uid_map) != 3 or uid_map[0] != "0" or uid_map[1] == "0" or uid_map[2] != "1":
                raise ValueError("netem requires single unprivileged-owner UID mapping")
            if (
                os.readlink("/proc/self/ns/net") == os.readlink("/proc/1/ns/net")
                or os.readlink("/proc/self/ns/user") == os.readlink("/proc/1/ns/user")
                or os.geteuid() != 0
            ):
                raise ValueError("netem requires isolated user AND network namespaces")
            report["netem_namespace"] = {
                "network": os.readlink("/proc/self/ns/net"),
                "user": os.readlink("/proc/self/ns/user"),
                "host_network": os.readlink("/proc/1/ns/net"),
                "uid_map": uid_map,
            }
        if hashlib.sha256(engine.read_bytes()).hexdigest() != ENGINE_SHA256:
            raise ValueError("Unreviewed engine")
        if (
            signer
            and hashlib.sha256(signer.read_bytes()).hexdigest()
            != "0f946753a72017954d2832c2a3bb311b5bae88b1a3d83042aa231132be06a32f"
        ):
            raise ValueError("Unreviewed TEST signer binary")
        if (
            evidence_tool
            and hashlib.sha256(evidence_tool.read_bytes()).hexdigest()
            != "4bd7295ff34b1d04133e652f9601d1d260f0aaac0dc36524befabf4f980e5948"
        ):
            raise ValueError("Unreviewed TEST evidence tool")
        if evidence_tool:
            report["evidence_tool_sha256"] = hashlib.sha256(evidence_tool.read_bytes()).hexdigest()
        native_status = subprocess.check_output(
            ["/usr/bin/git", "status", "--porcelain", "--untracked-files=normal", "--", "native"],
            cwd=ROOT,
            text=True,
        )
        report["native_source_clean"] = not native_status.strip()
        if require_clean_source and native_status.strip():
            raise ValueError("Native source must be committed and clean for frozen campaign")
        archive = output / "native-source.tar"
        subprocess.run(
            [
                "/usr/bin/git",
                "archive",
                "--format=tar",
                "--output",
                str(archive.resolve()),
                "HEAD",
                "native",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        report["source_archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
        subprocess.run(
            [str(engine), "testnet", "--v", "4", "--o", str(nodes_home)],
            check=True,
            capture_output=True,
        )
        base = choose_base()
        ports = [base + i * 10 + 1 for i in range(4)]
        ids = [
            subprocess.check_output(
                [str(engine), "show-node-id", "--home", str(nodes_home / f"node{i}")], text=True
            ).strip()
            for i in range(4)
        ]
        comet = json.loads((nodes_home / "node0/config/genesis.json").read_text())
        validators = sorted(
            [
                {
                    "public_key": base64.b64decode(v["pub_key"]["value"]).hex(),
                    "power": int(v["power"]),
                }
                for v in comet["validators"]
            ],
            key=lambda x: x["public_key"],
        )
        keys = [Ed25519PrivateKey.generate() for _ in range(3)]
        pubs = [public_key(key) for key in keys]
        registry = {
            p: {
                "institution_id": f"TEST-{i}",
                "controller_group": f"TEST-{i}",
                "payout_address": address(p),
                "label": "INSTITUTIONAL_VALIDATOR_TEST",
            }
            for i, p in enumerate(pubs[:2])
        }
        stamp = int(time.time())
        genesis = make_genesis(
            "tokoin-test-chaos-" + run_id.lower(), registry, address(pubs[2]), stamp, validators
        )
        guard(engine, genesis, [f"http://127.0.0.1:{p}" for p in ports])
        comet.update(
            chain_id=genesis["chain_id"],
            app_state=genesis,
            genesis_time=datetime.datetime.fromtimestamp(stamp, datetime.UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        )
        gp = home / "genesis.json"
        gp.write_bytes(canonical(genesis))
        (output / "app-genesis.json").write_bytes(canonical(genesis))
        (output / "comet-genesis.json").write_bytes(canonical(comet))
        report["source_commit"] = subprocess.check_output(
            ["/usr/bin/git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        report["dirty_source_hashes"] = {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "native").rglob("*.py"))
        }
        report["engine_sha256"] = ENGINE_SHA256
        report["genesis_sha256"] = hashlib.sha256(canonical(genesis)).hexdigest()
        mesh = ProxyMesh(base + 50, [base + i * 10 + 2 for i in range(4)])
        env = dict(os.environ, PYTHONPATH=str(ROOT / "native"))

        def spawn(args, filename):
            log = (output / filename).open("ab")
            logs.append(log)
            return subprocess.Popen(args, env=env, stdout=log, stderr=log)

        def start(i):
            if i == 3 and signer:
                for process in auxiliaries:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(10)
                auxiliaries.append(
                    spawn(
                        [
                            str(signer),
                            "--addr",
                            f"127.0.0.1:{base + 39}",
                            "--chain-id",
                            genesis["chain_id"],
                            "--key",
                            str(nodes_home / "node3/config/priv_validator_key.json"),
                            "--state",
                            str(nodes_home / "node3/data/priv_validator_state.json"),
                            "--control",
                            str(control),
                        ],
                        "signer-events.log",
                    )
                )

            nodes[i] = spawn(
                [str(engine), "start", "--home", str(nodes_home / f"node{i}")], f"node-{i}.log"
            )

        def height(i=0):
            if nodes[i].poll() is not None:
                raise ChildProcessError(f"node {i} exited {nodes[i].returncode}")
            return int(rpc(ports[i], "status")["sync_info"]["latest_block_height"])

        def heights():
            return [height(i) for i in range(4)]

        def progress(count=3):
            h = height()
            wait_for(lambda: height() >= h + count, seconds=max(60, count * 3))
            return {"from": h, "to": height()}

        def roots():
            target = min(heights()) - 1
            hashes = [rpc(p, "block", height=target)["block_id"]["hash"] for p in ports]
            assert len(set(hashes)) == 1, hashes
            return {"height": target, "block_hash": hashes[0]}

        def settle_halt(indices):
            time.sleep(4)
            before = [height(i) for i in indices]
            time.sleep(4)
            after = [height(i) for i in indices]
            assert before == after, (before, after)
            return {"before": before, "after": after, "observation_seconds": 4}

        for i in range(4):
            path = nodes_home / f"node{i}/config"
            (path / "genesis.json").write_bytes(canonical(comet))
            configure(
                path / "config.toml",
                {
                    ("", "proxy_app"): f'"tcp://127.0.0.1:{base + i * 10}"',
                    ("rpc", "laddr"): f'"tcp://127.0.0.1:{ports[i]}"',
                    ("p2p", "laddr"): f'"tcp://127.0.0.1:{base + i * 10 + 2}"',
                    ("p2p", "persistent_peers"): '"'
                    + ",".join(
                        f"{ids[j]}@127.0.0.1:{mesh.edges[i, j].port}" for j in range(4) if i != j
                    )
                    + '"',
                    ("p2p", "allow_duplicate_ip"): "true",
                    ("p2p", "pex"): "false",
                    ("p2p", "addr_book_strict"): "false",
                    ("p2p", "persistent_peers_max_dial_period"): '"1s"',
                    ("consensus", "timeout_commit"): '"100ms"',
                    ("consensus", "timeout_propose"): '"1s"',
                    ("", "log_level"): '"info"',
                },
            )
            if i == 3 and signer:
                configure(
                    path / "config.toml",
                    {("", "priv_validator_laddr"): f'"tcp://127.0.0.1:{base + 39}"'},
                )
            (output / f"node-{i}-config.toml").write_text((path / "config.toml").read_text())
            (home / f"app-{i}-faults.json").write_text("{}")
            apps[i] = spawn(
                [
                    sys.executable,
                    str(ROOT / "native/tools/chaos_abci.py"),
                    "--control",
                    str(home / f"app-{i}-faults.json"),
                    "--genesis",
                    str(gp),
                    "--db",
                    str(home / f"app-{i}.sqlite"),
                    "--port",
                    str(base + i * 10),
                ],
                f"app-{i}.log",
            )

        def ready_apps():
            for i, app in apps.items():
                if app.poll() is not None:
                    raise ChildProcessError(f"application {i} exited {app.returncode}")
                with socket.create_connection(("127.0.0.1", base + i * 10), timeout=1):
                    pass
            return True

        wait_for(ready_apps, 10)
        if signer:
            control = home / "faults.json"
            control.write_text("{}")
            report["signer_binary_sha256"] = hashlib.sha256(signer.read_bytes()).hexdigest()

            def signing_fault(**values):
                tmp = control.with_suffix(".tmp")
                tmp.write_text(json.dumps(values))
                tmp.replace(control)

            def observed_events(kind, **values):
                events = []
                for line in (output / "signer-events.log").read_text().splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("event") == kind and all(
                        event.get(k) == v for k, v in values.items()
                    ):
                        events.append(event)
                return events

        for i in range(4):
            start(i)
        wait_for(lambda: all(height(i) >= 4 for i in range(4)), 30)
        check("BFT-001", lambda: progress())

        def signed_load():
            started = time.monotonic()
            corpus = []
            initial_height = height()
            for n in range(20):
                tx = transaction(
                    keys[n % 2],
                    genesis,
                    n // 2 + 1,
                    "review_commit",
                    {
                        "reward_hash": hashlib.sha256(f"TEST-load-{n}".encode()).hexdigest(),
                        "commitment": hashlib.sha256(f"TEST-commit-{n}".encode()).hexdigest(),
                    },
                )
                receipt = rpc(ports[0], "broadcast_tx_commit", tx="0x" + canonical(tx).hex())
                assert receipt["check_tx"]["code"] == 0 and receipt["tx_result"]["code"] == 0, (
                    receipt
                )
                corpus.append({"transaction": tx, "receipt": receipt})
            elapsed = time.monotonic() - started
            (output / "signed-transaction-corpus.json").write_text(json.dumps(corpus, indent=2))
            return {
                "accepted_transactions": len(corpus),
                "elapsed_seconds": elapsed,
                "observed_transactions_per_second": len(corpus) / elapsed,
                "first_height": initial_height,
                "last_height": height(),
                "workload": "sequential signed review commitments; no rewards issued",
                "sustained_capacity_claim": False,
            }

        check("signed_transaction_load", signed_load)
        if netem_only:
            report["required_BFT_ids"] = ["BFT-001", "BFT-014"]

            def actual_netem_loss():
                start_height = height()
                subprocess.run(
                    ["/usr/sbin/tc", "qdisc", "add", "dev", "lo", "root", "netem", "loss", "5%"],
                    check=True,
                    capture_output=True,
                )
                try:
                    time.sleep(10)
                    stats = subprocess.check_output(
                        ["/usr/sbin/tc", "-s", "qdisc", "show", "dev", "lo"], text=True
                    )
                    dropped = sum(int(n) for n in re.findall(r"dropped (\d+)", stats))
                    assert dropped > 0, "No actual packet drop recorded"
                finally:
                    subprocess.run(
                        ["/usr/sbin/tc", "qdisc", "del", "dev", "lo", "root"],
                        check=True,
                        capture_output=True,
                    )
                wait_for(lambda: all(height(i) > start_height + 3 for i in range(4)), 90)
                return {"actual_kernel_packet_drops": dropped, "qdisc_statistics": stats, **roots()}

            check("BFT-014", actual_netem_loss)

            def actual_netem_reorder():
                start_height = height()
                subprocess.run(
                    [
                        "/usr/sbin/tc",
                        "qdisc",
                        "add",
                        "dev",
                        "lo",
                        "root",
                        "netem",
                        "delay",
                        "50ms",
                        "10ms",
                        "reorder",
                        "25%",
                        "50%",
                    ],
                    check=True,
                    capture_output=True,
                )
                try:
                    time.sleep(8)
                    stats = subprocess.check_output(
                        ["/usr/sbin/tc", "-s", "qdisc", "show", "dev", "lo"], text=True
                    )
                    assert "reorder 25%" in stats, stats
                finally:
                    subprocess.run(
                        ["/usr/sbin/tc", "qdisc", "del", "dev", "lo", "root"],
                        check=True,
                        capture_output=True,
                    )
                wait_for(lambda: all(height(i) > start_height + 3 for i in range(4)), 90)
                return {
                    "qdisc_statistics": stats,
                    "scope": "isolated namespace loopback only",
                    **roots(),
                }

            check("IP_packet_reordering", actual_netem_reorder)
            report["status"] = "PASS_NETEM_ONLY"
            return report

        nodes[3].kill()
        nodes[3].wait(10)
        check("BFT-002", lambda: progress())
        nodes[2].kill()
        nodes[2].wait(10)
        check("BFT-003", lambda: settle_halt([0, 1]))
        start(2)
        start(3)
        wait_for(lambda: all(height(i) > 4 for i in range(4)))
        check("crash_recovery", lambda: progress())
        mesh.faults(groups=[{0, 1, 2}, {3}])

        def three_one():
            progress()
            return settle_halt([3])

        check("BFT-004", three_one)
        mesh.faults()

        def converge():
            target = height() + 3
            wait_for(lambda: all(height(i) >= target for i in range(4)), 90)
            return roots()

        check("BFT-006", converge)
        mesh.faults(groups=[{0, 1}, {2, 3}])
        check("BFT-005", lambda: settle_halt([0, 1, 2, 3]))
        mesh.faults()
        check("BFT-007", converge)
        if signer:
            for skew in [60, -60]:
                signing_fault(skew_seconds=skew)

                def skew_check(skew=skew):
                    moved = progress(8)
                    events = observed_events("vote", skew_seconds=skew)
                    assert events, "No skewed vote observed"
                    return {
                        "votes": len(events),
                        "requested_vote_timestamp_offset_seconds": skew,
                        "OS_clock_changed": False,
                        **moved,
                        **roots(),
                    }

                check(f"vote_timestamp_skew_{skew}", skew_check)
            signing_fault(delay_ms=1000)

            def delay_check():
                moved = progress(8)
                events = observed_events("vote", delay_ms=1000)
                assert events, "No delayed vote observed"
                return {"delayed_votes": len(events), **moved, **roots()}

            check("BFT-011", delay_check)
            signing_fault(fail_proposal=True)

            def refusal_check():
                moved = progress(20)
                events = observed_events("proposal_refused")
                assert len(events) >= 2, "Insufficient actual proposal refusals"
                fault_heights = {event["height"] for event in events}
                round_changes = [
                    (int(h), int(r))
                    for h, r in re.findall(
                        r"height=(\d+) round=(\d+)", (output / "node-0.log").read_text()
                    )
                    if int(h) in fault_heights and int(r) > 0
                ]
                assert round_changes, "No actual round change observed after refusal"
                return {
                    "proposal_refusals": events,
                    "observed_round_changes": sorted(set(round_changes)),
                    "fault": "remote signer refuses proposals; not process disappearance",
                    **moved,
                    **roots(),
                }

            check("BFT-012", refusal_check)
            signing_fault()

        def app_fault(**values):
            path = home / "app-3-faults.json"
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(values))
            temp.replace(path)

        def app_events(i, kind):
            records = []
            for line in (output / f"app-{i}.log").read_text().splitlines():
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record.get("event") == kind:
                    records.append(record)
            return records

        app_fault(invalid_proposal=True)

        def invalid_proposal():
            moved = progress(12)
            injected = app_events(3, "invalid_proposal_injected")
            rejected = {str(i): app_events(i, "proposal_rejected") for i in range(3)}
            assert injected and all(rejected.values()), (
                "Missing invalid proposal or honest rejection"
            )
            return {"injected": injected, "honest_rejections": rejected, **moved, **roots()}

        check("BFT-009", invalid_proposal)
        app_fault(hold_proposal=True)

        def proposer_disappearance():
            wait_for(lambda: app_events(3, "proposal_held"), 30)
            held = app_events(3, "proposal_held")[-1]
            nodes[3].kill()
            nodes[3].wait(10)
            app_fault()
            moved = progress(4)
            start(3)
            return {"killed_proposer_while_ABCI_response_withheld": held, **moved, **converge()}

        check("BFT-008", proposer_disappearance)
        app_fault()
        nodes[3].send_signal(signal.SIGSTOP)
        check("SIGSTOP_one_validator", lambda: progress())
        nodes[3].send_signal(signal.SIGCONT)
        check("SIGCONT_recovery", converge)
        mesh.faults(delay=0.10)
        check("BFT-013", lambda: {"transport_chunk_delay_ms": 100, **progress()})
        mesh.faults(drop_every=5)
        time.sleep(5)
        drops = sum(e.dropped for e in mesh.edges.values())
        mesh.faults()

        def recover_loss():
            assert drops > 0, "No stream closure injected"
            return {"stream_closures": drops, **converge()}

        check("BFT-014_TCP_stream_loss_recovery", recover_loss)
        nodes[3].kill()
        nodes[3].wait(10)
        behind = height()
        progress(lag)
        start(3)
        check("BFT-015", lambda: {"lag_blocks": height() - behind, **converge()})
        check("same_chain_after_all_faults", roots)
        fresh = home / "fresh-node"
        subprocess.run(
            [str(engine), "init", "full", "--home", str(fresh)], check=True, capture_output=True
        )
        (fresh / "config/genesis.json").write_bytes(canonical(comet))
        configure(
            fresh / "config/config.toml",
            {
                ("", "proxy_app"): f'"tcp://127.0.0.1:{base + 40}"',
                ("rpc", "laddr"): f'"tcp://127.0.0.1:{base + 41}"',
                ("p2p", "laddr"): f'"tcp://127.0.0.1:{base + 42}"',
                ("p2p", "persistent_peers"): f'"{ids[0]}@127.0.0.1:{base + 2}"',
                ("p2p", "allow_duplicate_ip"): "true",
                ("p2p", "pex"): "false",
                ("p2p", "addr_book_strict"): "false",
            },
        )
        (output / "fresh-node-config.toml").write_text((fresh / "config/config.toml").read_text())
        auxiliaries.append(
            spawn(
                [
                    sys.executable,
                    "-m",
                    "tokoin_native.abci_server",
                    "--genesis",
                    str(gp),
                    "--db",
                    str(home / "app-4.sqlite"),
                    "--port",
                    str(base + 40),
                ],
                "app-4.log",
            )
        )
        time.sleep(0.5)
        auxiliaries.append(spawn([str(engine), "start", "--home", str(fresh)], "node-fresh.log"))

        def fresh_sync():
            target = height()
            wait_for(
                lambda: int(rpc(base + 41, "status")["sync_info"]["latest_block_height"]) >= target,
                120,
            )
            expected = rpc(ports[0], "block", height=target)
            observed = rpc(base + 41, "block", height=target)
            assert expected["block_id"] == observed["block_id"]
            assert (
                expected["block"]["header"]["app_hash"] == observed["block"]["header"]["app_hash"]
            )
            return {
                "synced_from_genesis_to_height": target,
                "block_hash": expected["block_id"]["hash"],
            }

        check("fresh_nonvalidator_sync", fresh_sync)
        if evidence_tool:

            def duplicate_vote():
                target = height() - 2
                commit = rpc(ports[0], "commit", height=target)
                signed_addresses = {
                    sig["validator_address"]
                    for sig in commit["signed_header"]["commit"]["signatures"]
                    if sig["block_id_flag"] == 2
                }
                selected = next(
                    i
                    for i in range(4)
                    if json.loads(
                        (nodes_home / f"node{i}/config/priv_validator_key.json").read_text()
                    )["address"]
                    in signed_addresses
                )
                public_commit = output / "double-sign-original-commit.json"
                public_commit.write_text(json.dumps(commit))
                generated = json.loads(
                    subprocess.check_output(
                        [
                            str(evidence_tool),
                            "--commit",
                            str(public_commit),
                            "--genesis",
                            str(output / "comet-genesis.json"),
                            "--key",
                            str(nodes_home / f"node{selected}/config/priv_validator_key.json"),
                            "--state",
                            str(nodes_home / f"node{selected}/data/priv_validator_state.json"),
                        ]
                    )
                )
                (output / "double-sign-evidence.json").write_text(json.dumps(generated, indent=2))
                accepted = rpc(
                    ports[0], "broadcast_evidence", evidence=json.dumps(generated["evidence"])
                )
                before = height()
                progress(4)
                included = []
                for h in range(before, height() + 1):
                    block = rpc(ports[0], "block", height=h)
                    if block["block"]["evidence"]["evidence"]:
                        included.append(h)
                assert included, "Evidence accepted but not observed in committed block"
                return {
                    "evidence_hash": generated["evidence_hash"],
                    "RPC_accepted": accepted,
                    "included_at_heights": included,
                    "both_signatures_verified": generated["both_signatures_verified"],
                    "punishment_asserted": False,
                    **roots(),
                }

            check("BFT-010", duplicate_vote)
        common = min(heights())
        with (output / "committed-hashes.jsonl").open("w") as out:
            for h in range(1, common + 1):
                blocks = [rpc(p, "block", height=h) for p in ports]
                row = {
                    "height": h,
                    "block_hashes": [b["block_id"]["hash"] for b in blocks],
                    "header_app_hashes": [b["block"]["header"]["app_hash"] for b in blocks],
                }
                assert len(set(row["block_hashes"])) == len(set(row["header_app_hashes"])) == 1
                out.write(json.dumps(row) + "\n")
        report["verified_common_heights"] = common
        for name, why in {
            "BFT-008": "Precise proposer disappearance needs hook; ordinary crash separately",
            "BFT-009": "Needs malicious proposer hook; invalid RPC tx is not equivalent",
            "BFT-010": "Network double-sign injection not implemented",
            "BFT-011": "Selective delayed votes requires decoded authenticated P2P hook",
            "BFT-012": "Repeated precise proposer failure hook unavailable",
            "BFT-014": "TCP stream loss recovery tested separately; raw IP packet loss unavailable",
            "clock_skew": "Static Go: LD_PRELOAD faketime unavailable; host clock untouched",
            "IP_packet_reordering": "TCP proxy cannot simulate IP reordering; firewall untouched",
        }.items():
            if name not in report["scenarios"]:
                report["scenarios"][name] = {"status": "UNSUPPORTED", "reason": why}
        report["status"] = "PARTIAL"
    except Exception as exc:
        report.update(status="FAIL", error=str(exc))
    finally:
        for i in range(5):
            dbpath = home / f"app-{i}.sqlite"
            if dbpath.exists():
                try:
                    connection = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)
                    with (output / f"app-{i}-hashes.jsonl").open("w") as stream:
                        for height_value, root in connection.execute(
                            "SELECT height,state_root FROM blocks ORDER BY height"
                        ):
                            stream.write(
                                json.dumps({"height": height_value, "state_hash": root}) + "\n"
                            )
                    connection.close()
                except Exception as error:
                    report.setdefault("capture_errors", []).append(str(error))
        for p in [*nodes.values(), *apps.values(), *auxiliaries]:
            if p.poll() is None:
                p.send_signal(signal.SIGCONT)
                p.terminate()
        for p in [*nodes.values(), *apps.values(), *auxiliaries]:
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        if mesh:
            mesh.close()
        for log in logs:
            log.close()
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        report["observed_resources"] = {
            "elapsed_seconds": time.monotonic() - started_monotonic,
            "children_user_cpu_seconds": usage.ru_utime,
            "children_system_cpu_seconds": usage.ru_stime,
            "max_single_child_rss_kib": usage.ru_maxrss,
            "aggregate_peak_memory_measured": False,
        }
        report["all_spawned_processes_stopped"] = all(
            p.poll() is not None for p in [*nodes.values(), *apps.values(), *auxiliaries]
        )
        persist()
        print(
            json.dumps({"report": str(output / "report.json"), "status": report["status"]}),
            flush=True,
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--signer", type=Path)
    parser.add_argument("--evidence-tool", type=Path)
    parser.add_argument("--netem-only", action="store_true")
    parser.add_argument("--require-clean-source", action="store_true")
    parser.add_argument("--lag-blocks", type=int, default=220)
    args = parser.parse_args()
    if args.lag_blocks < 200:
        parser.error("lag-blocks must be >=200")
    result = run(
        args.engine,
        args.output_root,
        args.lag_blocks,
        args.signer,
        args.evidence_tool,
        args.netem_only,
        args.require_clean_source,
    )
    sys.exit(1 if result["status"] == "FAIL" else 0)
