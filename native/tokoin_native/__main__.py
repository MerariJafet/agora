"""Read-only inspection of an existing local node journal."""

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path

from .core import metrics
from .explorer import render
from .store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "manifest", "export", "explorer"])
    parser.add_argument("--genesis", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    # SQLite backup through a read-only source: inspect a consistent isolated copy.
    with tempfile.TemporaryDirectory(prefix="tokoin-inspect-") as tmp:
        source = sqlite3.connect(args.db.resolve().as_uri() + "?mode=ro", uri=True)
        dest = sqlite3.connect(Path(tmp) / "copy.sqlite")
        source.backup(dest)
        source.close()
        dest.close()
        store = Store(Path(tmp) / "copy.sqlite", json.loads(args.genesis.read_text()))
        try:
            if args.command == "explorer":
                value = render(store)
            else:
                value = (
                    json.dumps(
                        {
                            "status": lambda: metrics(store.state),
                            "manifest": store.manifest,
                            "export": store.export,
                        }[args.command](),
                        sort_keys=True,
                        indent=2,
                    )
                    + "\n"
                )
            if args.output:
                args.output.write_text(value)
                print(f"VERIFIED {args.output.resolve()} {args.output.stat().st_size} bytes")
            else:
                print(value)
        finally:
            store.close()


if __name__ == "__main__":
    main()
