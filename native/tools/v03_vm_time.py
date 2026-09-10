#!/usr/bin/env python3
"""Four real KVM TEST kernels, local clocks and unmodified pinned CometBFT.
No guest default route, no host clock/network mutation. Runtime contains ephemeral keys.
"""

import argparse
import base64
import datetime
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "native"))
from chaos_proxy import ProxyMesh
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from run_network_test import configure, rpc, wait_for

from tokoin_native.core import (
    MATURITY,
    UNIT,
    VERSION,
    address,
    authorization_hash,
    canonical,
    distribution,
    make_genesis,
    merkle,
    review_commitment,
)
from tokoin_native.wallet import public_key, transaction

ENGINE = Path("/tmp/agora-native-build-20260909/bin/cometbft")  # noqa: S108 - verified pinned hash
ENGINE_HASH = "6edb2aa0f223e71758a48cf3d13d9d7ffd26f3357585bebe54311ba71f11ac3f"
PROFILES = (0, 60, -60, 300, -300, 1800, -1800)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy_file(source, root, target=None):
    target = root / (target or str(source)).lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build_root(runtime):
    root = runtime / "root"
    root.mkdir()
    for d in ("dev", "proc", "sys", "tmp", "run", "etc", "bin"):
        (root / d).mkdir(exist_ok=True)
    copy_file("/usr/bin/busybox", root, "/bin/busybox")
    copy_file(ENGINE, root, "/bin/cometbft")
    copy_file("/usr/bin/python3.12", root)
    shutil.copytree(
        "/usr/lib/python3.12",
        root / "usr/lib/python3.12",
        ignore=shutil.ignore_patterns("__pycache__", "test", "tests", "tkinter", "ensurepip"),
    )
    site = ROOT / ".venv/lib/python3.12/site-packages"
    for name in ("cryptography", "google", "_cffi_backend.cpython-312-x86_64-linux-gnu.so"):
        src = site / name
        if src.is_dir():
            shutil.copytree(src, root / "site" / name, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.exists():
            copy_file(src, root, "/site/" + name)
    shutil.copytree(
        ROOT / "native/tokoin_native",
        root / "native/tokoin_native",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    # Copy only linked runtime libraries; no credentials, home, package cache or host configuration.
    elf_files = [root / "usr/bin/python3.12", *root.rglob("*.so")]
    libraries = set()
    for path in elf_files:
        linked = subprocess.run(["/usr/bin/ldd", str(path)], capture_output=True, text=True).stdout
        libraries.update(re.findall(r"(/[^\s()]+)", linked))
    for lib in libraries:
        if Path(lib).is_file():
            copy_file(lib, root)
    copy_file(ROOT / "native/tools/v03_vm_guest.py", root, "/guest.py")
    kernel_version = "7.0.0-31-generic"
    kernel = runtime / "vmlinuz"
    with kernel.open("wb") as out:
        subprocess.run(
            ["/usr/bin/sudo", "-n", "cat", "/boot/vmlinuz-" + kernel_version],
            stdout=out,
            check=True,
        )
    module = (
        Path("/lib/modules")
        / kernel_version
        / "kernel/drivers/net/ethernet/intel/e1000/e1000.ko.zst"
    )
    with (root / "e1000.ko").open("wb") as out:
        subprocess.run(["/usr/bin/zstd", "-dc", str(module)], stdout=out, check=True)
    (root / "init").write_text("""#!/bin/busybox sh
/bin/busybox --install -s /bin
mount -t proc proc /proc
mount -t sysfs sys /sys
mount -t devtmpfs dev /dev
insmod /e1000.ko
ifconfig lo 127.0.0.1 up
ifconfig eth0 10.0.2.15 netmask 255.255.255.0 up
export PYTHONPATH=/native:/site
exec /usr/bin/python3.12 /guest.py
""")
    (root / "init").chmod(0o755)
    return root, kernel


def pack(root, target):
    # cpio paths generated locally, no shell substitution or secret-bearing outputs.
    names = ["."] + [str(p.relative_to(root)) for p in sorted(root.rglob("*"))]
    with target.open("wb") as out:
        subprocess.run(
            ["/usr/bin/cpio", "-o", "-H", "newc", "--quiet"],
            input=("\n".join(names) + "\n").encode(),
            cwd=root,
            stdout=out,
            check=True,
        )


def control(port, action=None, **kwargs):
    url = f"http://127.0.0.1:{port}/"
    data = None if action is None else json.dumps({"action": action, **kwargs}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as response:
        return json.load(response)


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix="agora-v03-vm-TEST-"))
    runtime.chmod(0o700)
    result = {
        "mode": "TEST_NON_RECOGNIZABLE",
        "runtime": str(runtime),
        "host_clock_modified": False,
        "vm_count": 4,
        "independent_operators": False,
        "status": "RUNNING",
        "profiles": [],
    }
    vms = []
    handles = []
    mesh = None
    try:
        assert sha(ENGINE) == ENGINE_HASH
        result["engine_sha256"] = sha(ENGINE)
        root, kernel = build_root(runtime)
        result["kernel_sha256"] = sha(kernel)
        runtime_inputs = {str(p.relative_to(root)): sha(p) for p in root.rglob("*") if p.is_file()}
        (output / "runtime-input-hashes.json").write_text(json.dumps(runtime_inputs, indent=2))
        result["runtime_input_manifest_sha256"] = sha(output / "runtime-input-hashes.json")
        result["host_start_time"] = time.time()
        result["host_monotonic_start"] = time.monotonic()
        result["harness_sha256"] = sha(Path(__file__))
        result["guest_supervisor_sha256"] = sha(ROOT / "native/tools/v03_vm_guest.py")
        with tarfile.open(output / "application-source.tar.gz", "w:gz") as archive:
            archive.add(root / "native", arcname="native")
        result["application_source_archive_sha256"] = sha(output / "application-source.tar.gz")
        result["source_files"] = {
            str(p.relative_to(root / "native")): sha(p) for p in (root / "native").rglob("*.py")
        }
        nodes = runtime / "nodes"
        subprocess.run(
            [str(ENGINE), "testnet", "--v", "4", "--o", str(nodes)], check=True, capture_output=True
        )
        ids = [
            subprocess.check_output(
                [str(ENGINE), "show-node-id", "--home", str(nodes / f"node{i}")], text=True
            ).strip()
            for i in range(4)
        ]
        raw = json.loads((nodes / "node0/config/genesis.json").read_text())
        validators = sorted(
            [
                {
                    "public_key": base64.b64decode(v["pub_key"]["value"]).hex(),
                    "power": int(v["power"]),
                }
                for v in raw["validators"]
            ],
            key=lambda v: v["public_key"],
        )
        keys = [Ed25519PrivateKey.generate() for _ in range(3)]
        pubs = [public_key(k) for k in keys]
        registry = {
            pubs[i]: {
                "institution_id": f"TEST-VM-{i}",
                "controller_group": f"TEST-VM-owner-{i}",
                "payout_address": address(pubs[i]),
                "label": "INSTITUTIONAL_VALIDATOR_TEST",
            }
            for i in (0, 1)
        }
        stamp = int(time.time()) - 3600
        genesis = make_genesis(
            "tokoin-test-v03-vm-time", registry, address(pubs[2]), stamp, validators
        )
        raw.update(
            chain_id=genesis["chain_id"],
            app_state=genesis,
            genesis_time=datetime.datetime.fromtimestamp(stamp, datetime.UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        )
        (output / "genesis.json").write_bytes(canonical(raw))
        (root / "app-genesis.json").write_bytes(canonical(genesis))
        base = 33100
        rpcports = [base + i * 10 + 1 for i in range(4)]
        controls = [base + i * 10 + 3 for i in range(4)]
        mesh = ProxyMesh(33200, [base + i * 10 + 2 for i in range(4)])
        for i in range(4):
            node = root / "node"
            if node.exists():
                shutil.rmtree(node)  # Own ephemeral staging only; never evidence/user directories.
            shutil.copytree(nodes / f"node{i}", node)
            (node / "config/genesis.json").write_bytes(canonical(raw))
            configure(
                node / "config/config.toml",
                {
                    ("", "proxy_app"): '"tcp://127.0.0.1:26658"',
                    ("rpc", "laddr"): '"tcp://0.0.0.0:26657"',
                    ("p2p", "laddr"): '"tcp://0.0.0.0:26656"',
                    ("p2p", "persistent_peers"): '"'
                    + ",".join(f"{ids[j]}@10.0.2.2:{33200 + i * 4 + j}" for j in range(4) if j != i)
                    + '"',
                    ("p2p", "allow_duplicate_ip"): "true",
                    ("p2p", "addr_book_strict"): "false",
                    ("p2p", "pex"): "false",
                    ("consensus", "timeout_commit"): '"500ms"',
                    ("", "log_level"): '"info"',
                },
            )
            shutil.copy2(node / "config/config.toml", output / f"node-{i}-config.toml")
            image = runtime / f"vm-{i}.cpio"
            pack(root, image)
            log = (output / f"vm-{i}-serial.log").open("wb")
            handles.append(log)
            args = [
                "qemu-system-x86_64",
                "-enable-kvm",
                "-cpu",
                "host",
                "-m",
                "768",
                "-smp",
                "1",
                "-nodefaults",
                "-no-reboot",
                "-nographic",
                "-serial",
                "stdio",
                "-kernel",
                str(kernel),
                "-initrd",
                str(image),
                "-append",
                "console=ttyS0 rdinit=/init agora_vm_test=1 quiet",
                "-netdev",
                (
                    f"user,id=n,hostfwd=tcp:127.0.0.1:{rpcports[i]}-:26657,"
                    f"hostfwd=tcp:127.0.0.1:{base + i * 10 + 2}-:26656,"
                    f"hostfwd=tcp:127.0.0.1:{controls[i]}-:8080"
                ),
                "-device",
                "e1000,netdev=n",
            ]
            vms.append(subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT))
        for p in controls:
            wait_for(lambda p=p: control(p), 90)
        result["guest_initial_clocks"] = [control(p) for p in controls]
        for p in controls:
            control(p, "clock", unix_time=time.time())
            control(p, "start")

        def height(i=0):
            return int(rpc(rpcports[i], "status")["sync_info"]["latest_block_height"])

        wait_for(lambda: min(height(i) for i in range(4)) >= 4, 90)

        def state(i=0):
            return json.loads(
                base64.b64decode(
                    rpc(rpcports[i], "abci_query", path='"/state"')["response"]["value"]
                )
            )

        corpus = []

        def send(actor, kind, payload, reject=False):
            current = state()
            tx = transaction(
                keys[actor],
                genesis,
                current["nonces"].get(address(pubs[actor]), 0) + 1,
                kind,
                payload,
            )
            response = rpc(rpcports[0], "broadcast_tx_commit", tx="0x" + canonical(tx).hex())
            corpus.append({"tx": tx, "response": response, "expected_reject": reject})
            (output / "transactions.json").write_text(json.dumps(corpus, indent=2))
            if reject:
                assert response["check_tx"]["code"] != 0, "unexpected monetary acceptance"
            else:
                assert response["check_tx"]["code"] == 0 and response["tx_result"]["code"] == 0, (
                    response
                )

        addresses = [address(p) for p in pubs]
        groups = {
            "proposer": {addresses[2]: 1},
            "solver": {addresses[2]: 1},
            "contributors": {addresses[2]: 1},
            "institutions": {addresses[0]: 1, addresses[1]: 1},
            "infra": {addresses[2]: 1},
        }
        allocation = distribution(UNIT, groups)
        body = {
            "reward_id": "TEST-VM-TIME",
            "research_id": "TEST-VM-CLOCK-FIXTURE",
            "candidate_version": 1,
            "protocol_version": VERSION,
            "genealogy_root": "a" * 64,
            "paper_hash": "b" * 64,
            "dataset_manifest_hash": "c" * 64,
            "code_manifest_hash": "d" * 64,
            "reward_total": UNIT,
            "groups": groups,
            "distribution_root": merkle([[k, v] for k, v in allocation.items()]),
            "participant_controllers": ["TEST-VM-researcher"],
        }
        rh = authorization_hash(body)
        for i in (0, 1):
            send(
                i,
                "review_commit",
                {"reward_hash": rh, "commitment": review_commitment(rh, "APPROVED", str(i) * 64)},
            )
        for i in (0, 1):
            send(
                i, "review_reveal", {"reward_hash": rh, "verdict": "APPROVED", "salt": str(i) * 64}
            )
        send(2, "authorize", body)
        result["reward_fixture"] = (
            "Explicit synthetic TEST monetary fixture, not scientific validation"
        )
        result["initial_locked_reward"] = state()["rewards"][body["reward_id"]]
        for skew in PROFILES:
            row = {"skew_seconds": skew, "skewed_validator": 3, "start_host_time": time.time()}
            result["profiles"].append(row)
            (output / "results.json").write_text(json.dumps(result, indent=2))
            row["clock_set_response"] = control(controls[3], "clock", unix_time=time.time() + skew)
            before = height()
            degraded = skew < -60
            expected_nodes = range(3) if degraded else range(4)
            wait_for(
                lambda before=before, expected_nodes=expected_nodes: (
                    min(height(i) for i in expected_nodes) >= before + 4
                ),
                90,
            )
            row["consensus_height"] = height()
            row["observed_guest_clock"] = control(controls[3])
            row["observed_host_clock"] = time.time()
            row["observed_skew_seconds"] = (
                row["observed_guest_clock"]["unix_time"] - row["observed_host_clock"]
            )
            assert abs(row["observed_skew_seconds"] - skew) < 3, "guest clock skew did not persist"
            send(2, "finalize", {"reward_id": body["reward_id"]}, reject=True)
            assert state()["rewards"][body["reward_id"]]["status"] == "LOCKED"
            row["premature_maturation_rejected"] = True
            control(controls[3], "stop")
            control(controls[3], "start")
            if degraded:
                time.sleep(6)
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{controls[3]}/logs", timeout=5
                ) as response:
                    faulty_logs = json.load(response)
                (output / f"profile-{skew}-faulty-node.log").write_text(faulty_logs["node"])
                assert "too far in the future" in faulty_logs["node"], (
                    "missing expected engine clock rejection"
                )
                row["skewed_node_behavior"] = "EXCLUDED_BY_ENGINE_CLOCK_TOLERANCE"
                try:
                    row["restart_under_skew_height"] = height(3)
                    row["restart_under_skew_rpc"] = "AVAILABLE"
                except (OSError, RuntimeError) as error:
                    row["restart_under_skew_rpc"] = "UNAVAILABLE"
                    row["restart_under_skew_error"] = repr(error)
            else:
                wait_for(lambda row=row: height(3) >= row["consensus_height"] + 3, 90)
                row["skewed_node_behavior"] = "PARTICIPATING"
            mesh.faults(groups=[[0, 1, 2], [3]])
            before = height()
            wait_for(lambda before=before: height() >= before + 3, 60)
            row["partition_3_1_height"] = height()
            mesh.faults()
            if degraded:
                row["guest_clock_correction"] = control(controls[3], "clock", unix_time=time.time())
                control(controls[3], "stop")
                control(controls[3], "start")
            wait_for(lambda row=row: height(3) >= row["partition_3_1_height"] + 2, 90)
            row["restart_height"] = height(3)
            common = min(height(i) for i in range(4)) - 1
            hashes = [
                rpc(p, "block", height=str(common))["block"]["header"]["app_hash"] for p in rpcports
            ]
            assert len(set(hashes)) == 1, "AppHash divergence"
            row.update(
                common_height=common, app_hashes=hashes, status="PASS", end_host_time=time.time()
            )
            (output / "results.json").write_text(json.dumps(result, indent=2))
        # Beyond the skew profiles: synthetic one-year advance inside all guests.
        # This validates chain-time semantics, never claims one calendar year elapsed.
        for p in controls:
            control(p, "clock", unix_time=time.time() + MATURITY + 120)
        target = result["initial_locked_reward"]["unlock_at"]
        wait_for(lambda: state()["time"] >= target, 90)
        send(2, "finalize", {"reward_id": body["reward_id"]})
        before = state()
        assert before["rewards"][body["reward_id"]]["status"] == "FINALIZED"
        control(controls[3], "clock", unix_time=time.time() - 1800)
        h = height()
        wait_for(lambda: min(height(i) for i in range(3)) >= h + 3, 90)
        after = state()
        assert after["rewards"][body["reward_id"]]["status"] == "FINALIZED"
        assert after["balances"] == before["balances"]
        result["post_finality_wall_clock_rewind"] = {
            "status": "PASS",
            "simulation": "All guest clocks advanced 365 days; no elapsed-year claim",
            "before": before,
            "after": after,
        }
        control(controls[3], "clock", unix_time=time.time() + MATURITY + 120)
        control(controls[3], "stop")
        control(controls[3], "start")
        wait_for(lambda: height(3) >= after["height"] + 2, 90)
        mesh.faults(groups=[[0, 1], [2, 3]])
        time.sleep(4)
        stopped = [height(i) for i in range(4)]
        time.sleep(4)
        assert [height(i) for i in range(4)] == stopped
        mesh.faults()
        wait_for(lambda: min(height(i) for i in range(4)) > max(stopped) + 2, 90)
        result["partition_2_2_recovery"] = {"status": "PASS", "halted_heights": stopped}
        common = min(height(i) for i in range(4)) - 1
        matrix = []
        for block_height in range(1, common + 1):
            blocks = [rpc(p, "block", height=str(block_height)) for p in rpcports]
            hashes = [b["block"]["header"]["app_hash"] for b in blocks]
            assert len(set(hashes)) == 1, f"AppHash divergence at {block_height}"
            matrix.append(
                {
                    "height": block_height,
                    "app_hashes": hashes,
                    "block_hashes": [b["block_id"]["hash"] for b in blocks],
                }
            )
        (output / "apphash-matrix.json").write_text(json.dumps(matrix, indent=2))
        result["all_height_apphash_consistency"] = {"status": "PASS", "heights": common}
        for i, p in enumerate(rpcports):
            export = rpc(p, "abci_query", path='"/explorer"')["response"]
            (output / f"node-{i}-application-export.json").write_bytes(
                base64.b64decode(export["value"])
            )
        result["status"] = "PASS"
    except Exception as error:
        result["status"] = "FAIL"
        result["failure"] = repr(error)
        raise
    finally:
        if mesh:
            mesh.close()
        for i in range(len(vms)):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{33103 + i * 10}/logs", timeout=3
                ) as response:
                    logs = json.load(response)
                for name, content in logs.items():
                    (output / f"vm-{i}-{name}.log").write_text(content)
            except Exception as error:
                result.setdefault("log_collection_failures", []).append(str(error))
        for vm in vms:
            if vm.poll() is None:
                vm.terminate()
                vm.wait(timeout=15)
        for handle in handles:
            handle.close()
        result["host_end_time"] = time.time()
        result["host_monotonic_end"] = time.monotonic()
        (output / "results.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {"status": result["status"], "profiles": len(result["profiles"]), "output": str(output)}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output.resolve())
