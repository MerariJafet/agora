#!/usr/bin/env python3
"""Capture AGORA critical invariants without treating live activity as drift."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agora_api.db import SessionLocal
from agora_api.scoped_invariants import capture_snapshot_manifest
from sqlalchemy import text


async def _event_count() -> int:
    async with SessionLocal() as session:
        return int((await session.execute(text("SELECT count(*) FROM events"))).scalar_one())


async def _capture(args: argparse.Namespace) -> dict:
    before_events = int(args.before_event_count) if args.before_event_count is not None else None
    async with SessionLocal() as session:
        snapshot = await capture_snapshot_manifest(
            session,
            provenance_scope=args.provenance_scope,
            before_event_count=before_events,
        )
    output = Path(args.output).expanduser() if args.output else None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    parser.add_argument("--provenance-scope", default="critical")
    parser.add_argument("--before-event-count", type=int)
    parser.add_argument("--print-event-count", action="store_true")
    args = parser.parse_args()
    if args.print_event_count:
        print(asyncio.run(_event_count()))
        return 0
    print(json.dumps(asyncio.run(_capture(args)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
