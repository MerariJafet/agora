#!/usr/bin/env python3
"""Reproduce TEST helpers from two source paths; require equal binary hashes."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

COMMIT = "94d77f9f51a72e2b7d832798859f6222f08028f8"
FLAGS = ["build", "-p=4", "-mod=readonly", "-trimpath", "-buildvcs=false", "-ldflags=-buildid="]


def build(cache, output, report):
    env = dict(
        os.environ,
        GOTOOLCHAIN="local",
        GOROOT=str(cache / "go"),
        GOPATH=str(cache / "gopath"),
        GOCACHE=str(cache / "go-cache"),
        CGO_ENABLED="0",
        GOOS="linux",
        GOARCH="amd64",
        GOAMD64="v1",
        GOFLAGS="",
        GOWORK="off",
        GOMAXPROCS="4",
        GOPROXY="off",
        GOSUMDB="off",
    )
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"mode": "TEST_HELPERS", "flags": FLAGS, "builds": {}, "status": "RUNNING"}
    try:
        for source_name, binary_name in [
            ("chaos_signer.go", "chaos-signer"),
            ("chaos_network_evidence.go", "chaos-evidence"),
            ("chaos_double_sign.go", "chaos-double-sign"),
        ]:
            source = Path(__file__).with_name(source_name)
            hashes = []
            for index in range(2):
                with tempfile.TemporaryDirectory(
                    prefix=f"agora-helper-source-{index}-"
                ) as directory:
                    copied = Path(directory) / source_name
                    copied.write_bytes(source.read_bytes())
                    target = Path(directory) / binary_name
                    subprocess.run(
                        [str(cache / "go/bin/go"), *FLAGS, "-o", str(target), str(copied)],
                        cwd=cache / f"cometbft-{COMMIT}",
                        env=env,
                        check=True,
                        capture_output=True,
                    )
                    hashes.append(hashlib.sha256(target.read_bytes()).hexdigest())
                    if index == 0:
                        shutil.copyfile(target, output / binary_name)
                        (output / binary_name).chmod(0o700)
            if len(set(hashes)) != 1:
                raise RuntimeError(f"Path-dependent build: {source_name}: {hashes}")
            evidence["builds"][binary_name] = {
                "sha256": hashes[0],
                "two_path_hashes": hashes,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        evidence["status"] = "PASS"
    except Exception as error:
        evidence.update(status="FAIL", error=str(error))
        raise
    finally:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(evidence, indent=2) + "\n")
        print(json.dumps(evidence), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    build(args.cache.resolve(), args.output.resolve(), args.report.resolve())
