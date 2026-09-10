#!/usr/bin/env python3
"""Replay VM application exports using exactly the archived application source.
This validates native application transitions; it is not a CometBFT light client.
"""

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from v03_vm_verify import verify

REPLAY = """
import json,sys,tempfile
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from tokoin_native.core import digest, require
from tokoin_native.store import Store
export=json.loads(Path(sys.argv[2]).read_text())
genesis=json.loads(Path(sys.argv[3]).read_text())["app_state"]
require(export["genesis"]==genesis,"untrusted genesis")
with tempfile.TemporaryDirectory(prefix="tokoin-v03-vm-replay-") as tmp:
 store=Store(Path(tmp)/"verify.sqlite",genesis)
 for block in export["blocks"]:
  store.prepare(block["transactions"],block["height"],block["timestamp"])
  require(store.pending[1]==block,"application block mismatch")
  store.commit()
 print(json.dumps({
  "height":store.state["height"],
  "state_root":digest("tokoin.state.v2",store.state),
  "created_units":store.state["created"],
  "rewards":{k:v["status"] for k,v in store.state["rewards"].items()},
  "consensus_signatures_verified":False}))
 store.close()
"""


def run(directory):
    directory = directory.resolve()
    verify(directory)
    records = []
    with tempfile.TemporaryDirectory(prefix="v03-vm-source-replay-") as tmp:
        with tarfile.open(directory / "application-source.tar.gz") as archive:
            members = archive.getmembers()
            if any(not m.name.startswith("native") or m.issym() or m.islnk() for m in members):
                raise ValueError("unexpected application source archive member")
            archive.extractall(tmp, filter="data")
        env = dict(os.environ, AGORA_ENV="test")
        for node in range(4):
            response = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    REPLAY,
                    str(Path(tmp) / "native"),
                    str(directory / f"node-{node}-application-export.json"),
                    str(directory / "genesis.json"),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=env,
                timeout=90,
            )
            records.append({"node": node, **json.loads(response.stdout)})
    return {
        "status": "PASS",
        "source": "application-source.tar.gz",
        "independent_processes": 4,
        "independent_machines": False,
        "records": records,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.directory), indent=2))
