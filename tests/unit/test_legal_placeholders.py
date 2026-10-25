"""The legal-placeholder guard decides whether a release may go out, so it is
pinned against synthetic pages, not against the current drafts."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_legal_placeholders.py"
spec = importlib.util.spec_from_file_location("agora_legal_guard", SCRIPT)
assert spec is not None and spec.loader is not None
guard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def _page(root: Path, name: str, body: str) -> None:
    path = root / "apps" / "web" / "app" / name / "page.tsx"
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")


def test_placeholders_block_the_release(tmp_path):
    _page(tmp_path, "privacy",
          "<p>Domicilio: [PENDIENTE: domicilio del responsable]</p>\n<p>RFC [RFC]</p>")
    _page(tmp_path, "terms", "<p>Versión 0.1 — borrador pendiente de revisión legal.</p>")
    hits = guard.find_placeholders(tmp_path)
    found = [(h[0].split("/")[3], h[1]) for h in hits]
    assert found == [("privacy", 1), ("privacy", 2), ("terms", 1)]
    assert guard.main([str(tmp_path)]) == 1


def test_complete_pages_pass(tmp_path):
    _page(tmp_path, "privacy", "<p>Responsable: Ejemplo S.A. de C.V., RFC EJE010101AAA.</p>")
    _page(tmp_path, "terms", "<p>Versión 1.0. Última actualización: 1 de noviembre de 2026.</p>")
    assert guard.find_placeholders(tmp_path) == []
    assert guard.main([str(tmp_path)]) == 0


def test_missing_pages_are_not_placeholders(tmp_path):
    assert guard.main([str(tmp_path)]) == 0


def test_placeholder_wrapped_across_lines_is_found(tmp_path):
    _page(tmp_path, "privacy", "<p>Domicilio: [PENDIENTE:\n  domicilio]</p>")
    hits = guard.find_placeholders(tmp_path)
    assert hits and hits[0][1] == 1 and hits[0][2] == "[PENDIENTE: domicilio]"
