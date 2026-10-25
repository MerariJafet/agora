"""Refuse to publish legal pages that still carry placeholders.

Lesson of the 2026-10 portfolio review: legal notices went live with
"[RFC]", "[DOMICILIO]" or "pendiente". The responsible party's data (name,
RFC, address, ARCO e-mail) only comes from the owner, so until it is filled
in, release.sh runs this check and refuses the deploy.

    python scripts/check_legal_placeholders.py [repo_root]   # exit 1 if any

Standard library only (runs on the VM's Python 3.10).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LEGAL_PAGES = ("apps/web/app/privacy/page.tsx", "apps/web/app/terms/page.tsx")

# Bracketed placeholders and the explicit draft wording used in the drafts.
PLACEHOLDER = re.compile(
    r"\[(?:PENDIENTE|TODO|RFC|DOMICILIO|RAZ[OÓ]N SOCIAL|CORREO)[^\]]*\]"
    r"|borrador pendiente de revisi[oó]n legal",
    re.IGNORECASE,
)


def find_placeholders(root: Path) -> list[tuple[str, int, str]]:
    hits = []
    for rel in LEGAL_PAGES:
        path = root / rel
        if not path.exists():
            continue
        # Whole-file scan: a placeholder wrapped across lines must still count.
        text = path.read_text(encoding="utf-8")
        for match in PLACEHOLDER.finditer(text):
            number = text.count("\n", 0, match.start()) + 1
            hits.append((rel, number, " ".join(match.group(0).split())))
    return hits


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    hits = find_placeholders(root)
    for rel, number, text in hits:
        print(f"PLACEHOLDER {rel}:{number}: {text}")
    if hits:
        print("Legal pages are not publishable yet: the owner must supply the missing data.")
        return 1
    print("legal pages: no placeholders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
