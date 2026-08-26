#!/usr/bin/env python3
"""Create/apply the owner-authorized P1 provenance adjudication manifest."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agora_api.db import SessionLocal
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID, COLLATZ_SPACE_ID
from agora_api.provenance import provenance_counts
from agora_api.provenance_adjudication import (
    DEFAULT_AUTHORIZED_AGENT_NAMES,
    apply_adjudication_manifest,
    build_adjudication_manifest,
)


def _configured_ids(agent_base: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for child in sorted(agent_base.iterdir()) if agent_base.exists() else []:
        config_path = child / "config.json"
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            continue
        name = config.get("agent_name")
        agent_id = config.get("agent_id")
        if name in DEFAULT_AUTHORIZED_AGENT_NAMES and agent_id:
            result[str(name)] = str(agent_id)
    return result


async def _run(args: argparse.Namespace) -> dict:
    async with SessionLocal() as session:
        manifest = await build_adjudication_manifest(
            session,
            configured_agent_ids=_configured_ids(Path(args.agent_base).expanduser()),
            mission_id=args.mission_id,
            space_id=args.space_id,
            target_class=args.target_class,
        )
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        result = {
            "mode": "dry-run",
            "manifest_path": str(output_path),
            "manifest_hash": manifest["manifest_hash"],
            "agent_ids": manifest["agent_ids"],
            "record_count": len(manifest["records"]),
        }
        if args.apply:
            apply_result = await apply_adjudication_manifest(session, manifest)
            await session.commit()
            result |= {
                "mode": "apply",
                "apply_result": apply_result,
                "provenance_counts": await provenance_counts(session),
            }
        else:
            await session.rollback()
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--agent-base", default="/home/merari-acero/.agora-agents")
    parser.add_argument("--mission-id", default=COLLATZ_MISSION_ID)
    parser.add_argument("--space-id", default=COLLATZ_SPACE_ID)
    parser.add_argument("--target-class", default="real")
    parser.add_argument(
        "--output",
        default="/home/merari-acero/agora/docs/work/p1-current-experiment-provenance.json",
    )
    args = parser.parse_args()
    print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
