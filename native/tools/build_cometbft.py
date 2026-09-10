#!/usr/bin/env python3
"""Build pinned official CometBFT outside the repository; never initializes nodes/keys.
Network reads occur only during preparation. --offline requires downloaded inputs
and Go modules already cached. Produced binary is a development dependency.
"""

import argparse
import hashlib
import json
import os
import subprocess
import tarfile
import urllib.request
from pathlib import Path

COMMIT = "94d77f9f51a72e2b7d832798859f6222f08028f8"
SOURCE_SHA256 = "0269ac18fe3f79b902232f7bf8d6afe4145316555f00c5e80fe58250e3e6c9c7"
GO_VERSION = "go1.27.1"
GO_SHA256 = "63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445"


def sha(path):
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def fetch(url, path, expected, offline):
    if not url.startswith("https://"):
        raise ValueError("Only fixed official HTTPS sources are allowed")
    if not path.exists():
        if offline:
            raise RuntimeError(f"Offline input missing: {path}")
        partial = path.with_suffix(".partial")
        with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as out:  # noqa: S310
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        partial.rename(path)
    if sha(path) != expected:
        raise RuntimeError(f"Checksum mismatch: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache", type=Path, default=Path.home() / ".cache/agora-native-build/v0.38.26"
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    root = args.cache.resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_url = f"https://codeload.github.com/cometbft/cometbft/tar.gz/{COMMIT}"
    go_url = f"https://go.dev/dl/{GO_VERSION}.linux-amd64.tar.gz"
    for filename, url, expected, target in [
        ("cometbft.tar.gz", source_url, SOURCE_SHA256, root / f"cometbft-{COMMIT}"),
        ("go.tar.gz", go_url, GO_SHA256, root / "go"),
    ]:
        archive = root / filename
        fetch(url, archive, expected, args.offline)
        if not target.exists():
            with tarfile.open(archive) as stream:
                stream.extractall(root, filter="data")
    source = root / f"cometbft-{COMMIT}"
    env = dict(
        os.environ,
        GOTOOLCHAIN="local",
        GOROOT=str(root / "go"),
        GOPATH=str(root / "gopath"),
        GOCACHE=str(root / "go-cache"),
        CGO_ENABLED="0",
        GOOS="linux",
        GOARCH="amd64",
        GOAMD64="v1",
        GOFLAGS="",
        GOWORK="off",
        GOMAXPROCS="4",
    )
    if args.offline:
        env.update(GOPROXY="off", GOSUMDB="off")
    binary = root / "bin" / "cometbft"
    binary.parent.mkdir(exist_ok=True)
    command = [
        str(root / "go/bin/go"),
        "build",
        "-p=4",
        "-mod=readonly",
        "-trimpath",
        "-buildvcs=false",
        "-ldflags=-buildid=",
        "-o",
        str(binary),
        "./cmd/cometbft",
    ]
    subprocess.run(command, cwd=source, env=env, check=True)  # noqa: S603 - pinned Go, no shell
    report = dict(
        engine="CometBFT",
        version="v0.38.26",
        commit=COMMIT,
        source_url=source_url,
        source_sha256=SOURCE_SHA256,
        go_version=GO_VERSION,
        go_url=go_url,
        go_sha256=GO_SHA256,
        go_mod_sha256=sha(source / "go.mod"),
        go_sum_sha256=sha(source / "go.sum"),
        binary=str(binary),
        binary_sha256=sha(binary),
        command=command,
        status="BUILT_LOCAL_NOT_PRODUCTION_AUDIT",
        private_keys_created=False,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
