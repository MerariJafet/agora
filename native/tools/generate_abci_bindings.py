#!/usr/bin/env python3
"""Generate namespaced Python ABCI 2.0 bindings from pinned official schemas.
Run with isolated proto-tools Python after build_cometbft.py populated its cache.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import grpc_tools

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path.home() / ".cache/agora-native-build/v0.38.26"
COMMIT = "94d77f9f51a72e2b7d832798859f6222f08028f8"
SOURCE = CACHE / f"cometbft-{COMMIT}"
GOGO = CACHE / "gopath/pkg/mod/github.com/cosmos/gogoproto@v1.7.0"
VENDOR = ROOT / "native/tokoin_native/vendor"
INCLUDES = [SOURCE / "proto", GOGO, Path(grpc_tools.__file__).parent / "_proto"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    source = args.cache / f"cometbft-{COMMIT}"
    gogo = args.cache / "gopath/pkg/mod/github.com/cosmos/gogoproto@v1.7.0"
    includes = [source / "proto", gogo, Path(grpc_tools.__file__).parent / "_proto"]
    seen = {}

    def visit(name):
        if name in seen or name.startswith("google/protobuf/"):
            return
        path = next((p / name for p in includes if (p / name).is_file()), None)
        if path is None:
            raise RuntimeError(f"Missing official import: {name}")
        seen[name] = path
        for dependency in re.findall(r'^import\s+"([^"]+)";', path.read_text(), re.M):
            visit(dependency)

    visit("tendermint/abci/types.proto")
    VENDOR.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        *[f"-I{p}" for p in includes],
        f"--python_out={VENDOR}",
        f"--pyi_out={VENDOR}",
        *sorted(seen),
    ]
    subprocess.run(command, check=True)  # noqa: S603 - fixed protoc module, no shell
    for path in sorted([*VENDOR.rglob("*_pb2.py"), *VENDOR.rglob("*_pb2.pyi")]):
        text = path.read_text()
        for package in ["tendermint", "gogoproto"]:
            text = text.replace(f"from {package}", f"from tokoin_native.vendor.{package}")
        if path.suffix == ".pyi":
            # protoc emits ClassVar at module scope for extension field constants.
            text = re.sub(r"^([A-Z_]+): _ClassVar\[int\]$", r"\1: int", text, flags=re.M)
        path.write_text(text)
        parent = path.parent
        while parent != VENDOR.parent:
            (parent / "__init__.py").touch(exist_ok=True)
            parent = parent.parent
    (VENDOR / "COMETBFT_LICENSE").write_text((source / "LICENSE").read_text())
    (VENDOR / "GOGOPROTO_LICENSE").write_text((gogo / "LICENSE").read_text())
    report = {
        "cometbft_commit": COMMIT,
        "gogoproto_version": "v1.7.0",
        "grpcio_tools": "1.78.0",
        "protobuf_runtime_minimum": "6.31.1",
        "transform": (
            "Imports namespaced; generated pyi module-level ClassVar[int] "
            "constants normalized to int"
        ),
        "source_schemas": {
            n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in sorted(seen.items())
        },
        "generated_files": {
            str(p.relative_to(VENDOR)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted([*VENDOR.rglob("*_pb2.py"), *VENDOR.rglob("*_pb2.pyi")])
        },
    }
    (VENDOR / "PROVENANCE.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
