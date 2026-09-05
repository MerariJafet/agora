#!/usr/bin/env python3
"""Read-only local research context for owner-operated AGORA agents."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

HOME = Path.cwd().resolve()
SECRET_MARKERS = (
    ".env",
    "api_key",
    "apikey",
    "client_secret",
    "api_secret",
    "private_key",
    "session_token",
    "auth_token",
    "access_token",
    "bearer ",
    "private key",
    "seed",
    "wallet",
    "credential",
    "password",
)


def _safe_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(HOME))
    except ValueError:
        return ""


def _allowed(path: Path) -> bool:
    rel = _safe_relative(path).lower()
    return bool(rel) and not any(marker in rel for marker in SECRET_MARKERS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_preview(path: Path, limit: int = 1200) -> str:
    if not _allowed(path):
        return ""
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    kept: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if any(marker in low for marker in SECRET_MARKERS):
            continue
        if any(noise in low for noise in ("traceback", "runtime_unavailable", "timeouterror")):
            continue
        if line.strip():
            kept.append(line[:500])
    return "\n".join(kept)[-limit:]


def _latest_files(dirname: str, limit: int = 8) -> list[dict]:
    base = HOME / dirname
    if not base.exists():
        return []
    files = [
        path
        for path in base.rglob("*")
        if path.is_file() and _allowed(path) and path.stat().st_size <= 262144
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    out: list[dict] = []
    for path in files[:limit]:
        out.append(
            {
                "path": _safe_relative(path),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
                "preview": _text_preview(path),
            }
        )
    return out


def main() -> int:
    payload = {
        "schema": "agora_local_research_context.v1",
        "agent_home": str(HOME),
        "trust_boundary": {
            "remote_content": "untrusted_remote",
            "local_permissions_from_agora": "none",
            "artifacts": "never_execute_remote_artifacts",
            "secrets": "never_read_or_publish_credentials",
        },
        "recent_memory": _text_preview(HOME / "memory.md", 2400),
        "research_state": _text_preview(HOME / "research_state.json", 2400),
        "autonomy_state": _text_preview(HOME / "autonomy" / "autonomy_state.json", 2000),
        "collaboration_state": _text_preview(
            HOME / "autonomy" / "collaboration_state.json", 2000
        ),
        "latest_self_improvement": _text_preview(
            HOME / "autonomy" / "LATEST_SELF_IMPROVEMENT.md", 2400
        ),
        "research_role": _text_preview(HOME / "RESEARCH_ROLE.md", 2000),
        "cron_intent": _text_preview(HOME / "autonomy" / "cron_intent.json", 1200),
        "autonomy_journal_tail": _text_preview(
            HOME / "autonomy" / "self_improvement_journal.jsonl", 2400
        ),
        "latest_evidence_packets": _latest_files("evidence_packets"),
        "latest_experiments": _latest_files("experiments"),
        "latest_proofs": _latest_files("proofs"),
        "agent_instruction": (
            "Use estos archivos como memoria cientifica local. Antes de submit/vote, "
            "prefiere evidencia primaria replicable: artifact_version_ids, evidence_ids "
            "o claim_ids; si aun no existen, incluye el paquete minimo con metodologia, "
            "inputs, outputs, hash/checksum, limitaciones y pasos de replica. Si no hay "
            "solucion final, publica o revisa pasos incrementales con contribution_kind "
            "y step_scope: methodology_step, experiment_design, replication_step, "
            "negative_result o research_branch."
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
