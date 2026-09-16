"""The metrics collector is what keeps published counts honest, so it is tested
against a synthetic tree rather than against the real repository: these tests
must not change their verdict when someone adds an ADR or an MCP tool."""

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "collect_metrics.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("agora_collect_metrics", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


collect_metrics = _load_module()


def _build_tree(root: Path, *, tools: int = 3, adrs: int = 2, migrations: int = 2) -> None:
    """Lay down a miniature AGORA checkout with known, arbitrary counts."""
    server = root / "bridge" / "agora_bridge"
    server.mkdir(parents=True)
    body = "\n\n".join(
        f'@server.tool(name="agora_tool_{index}")\nasync def tool_{index}() -> None: ...'
        for index in range(tools)
    )
    (server / "mcp_server.py").write_text(f"server = object()\n\n{body}\n", encoding="utf-8")

    adr_dir = root / "docs" / "adr"
    adr_dir.mkdir(parents=True)
    for index in range(1, adrs + 1):
        (adr_dir / f"ADR-{index:04d}-decision-{index}.md").write_text("# ADR\n", encoding="utf-8")

    versions = root / "apps" / "api" / "alembic" / "versions"
    versions.mkdir(parents=True)
    for index in range(1, migrations + 1):
        migration = versions / f"{index:04d}_change_{index}.py"
        migration.write_text("revision = 'x'\n", encoding="utf-8")
    # Noise that must never be counted as a migration.
    (versions / "__init__.py").write_text("", encoding="utf-8")
    (versions / "__pycache__").mkdir()
    (versions / "__pycache__" / "0001_change_1.py").write_text("", encoding="utf-8")


def _metrics(root: Path) -> dict:
    return collect_metrics.build_metrics(root, collect_tests=False)


def test_tool_count_matches_synthetic_server(tmp_path: Path):
    _build_tree(tmp_path, tools=7)

    assert collect_metrics.count_mcp_tools(tmp_path) == 7


def test_tool_count_matches_the_real_bridge_server():
    """Guards the decorator pattern itself: if the Bridge stops using
    ``@server.tool``, the count would silently collapse to zero."""
    source = (REPO_ROOT / "bridge" / "agora_bridge" / "mcp_server.py").read_text(encoding="utf-8")

    assert collect_metrics.count_mcp_tools(REPO_ROOT) == source.count("@server.tool")
    assert collect_metrics.count_mcp_tools(REPO_ROOT) > 0


def test_migrations_exclude_pycache_and_package_files(tmp_path: Path):
    _build_tree(tmp_path, migrations=4)

    names = [path.name for path in collect_metrics.migration_files(tmp_path)]

    assert names == ["0001_change_1.py", "0002_change_2.py", "0003_change_3.py", "0004_change_4.py"]
    assert _metrics(tmp_path)["latest_migration"] == "0004_change_4"


def test_adr_range_reports_numbering_not_file_count(tmp_path: Path):
    _build_tree(tmp_path, adrs=3)
    # A duplicate number: three distinct numbers, four files.
    (tmp_path / "docs" / "adr" / "ADR-0003-second-take.md").write_text("# ADR\n", encoding="utf-8")

    metrics = _metrics(tmp_path)

    assert metrics["counts"]["adrs"] == 4
    assert metrics["adr_range"] == {"lowest": "ADR-0001", "highest": "ADR-0003"}


def test_write_then_check_is_clean(tmp_path: Path):
    _build_tree(tmp_path)
    collect_metrics.write(tmp_path, _metrics(tmp_path))

    assert collect_metrics.check(tmp_path, _metrics(tmp_path)) == []


def test_check_detects_drift_when_the_tree_grows(tmp_path: Path):
    _build_tree(tmp_path, tools=3)
    collect_metrics.write(tmp_path, _metrics(tmp_path))

    server = tmp_path / "bridge" / "agora_bridge" / "mcp_server.py"
    added = '\n@server.tool(name="agora_new")\nasync def new_tool() -> None: ...\n'
    server.write_text(server.read_text(encoding="utf-8") + added, encoding="utf-8")

    problems = collect_metrics.check(tmp_path, _metrics(tmp_path))

    assert any("mcp_tools" in problem for problem in problems)


def test_check_detects_a_stale_injected_block(tmp_path: Path):
    _build_tree(tmp_path)
    doc = tmp_path / "OVERVIEW.md"
    doc.write_text(
        f"# Doc\n\n{collect_metrics.START_MARKER}\n{collect_metrics.END_MARKER}\n",
        encoding="utf-8",
    )
    collect_metrics.write(tmp_path, _metrics(tmp_path))

    doc.write_text(
        doc.read_text(encoding="utf-8").replace("**3** MCP tools", "**999** MCP tools"),
        encoding="utf-8",
    )

    problems = collect_metrics.check(tmp_path, _metrics(tmp_path))

    assert any("OVERVIEW.md" in problem for problem in problems)


def test_check_writes_nothing(tmp_path: Path):
    _build_tree(tmp_path)
    doc = tmp_path / "OVERVIEW.md"
    doc.write_text(
        f"# Doc\n\n{collect_metrics.START_MARKER}\n{collect_metrics.END_MARKER}\n",
        encoding="utf-8",
    )
    collect_metrics.write(tmp_path, _metrics(tmp_path))
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    exit_code = collect_metrics.main(
        ["--check", "--no-collect-tests", "--root", str(tmp_path)]
    )

    assert exit_code == 0
    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before


def test_check_exits_nonzero_on_drift(tmp_path: Path):
    _build_tree(tmp_path)
    collect_metrics.write(tmp_path, _metrics(tmp_path))
    metrics_path = tmp_path / collect_metrics.METRICS_FILENAME
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    payload["counts"]["adrs"] = 999
    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    exit_code = collect_metrics.main(
        ["--check", "--no-collect-tests", "--root", str(tmp_path)]
    )

    assert exit_code == 1


def test_injection_is_idempotent(tmp_path: Path):
    _build_tree(tmp_path)
    block = collect_metrics.render_block(_metrics(tmp_path))
    original = (
        f"# Doc\n\nbefore\n\n{collect_metrics.START_MARKER}\n"
        f"stale text\n{collect_metrics.END_MARKER}\n\nafter\n"
    )

    once = collect_metrics.inject(original, block)
    twice = collect_metrics.inject(once, block)

    assert once == twice
    assert "stale text" not in once
    assert once.startswith("# Doc\n\nbefore\n")
    assert once.endswith("\nafter\n")


def test_running_write_twice_changes_nothing_the_second_time(tmp_path: Path):
    _build_tree(tmp_path)
    doc = tmp_path / "OVERVIEW.md"
    doc.write_text(
        f"# Doc\n\n{collect_metrics.START_MARKER}\n{collect_metrics.END_MARKER}\n",
        encoding="utf-8",
    )

    first = collect_metrics.write(tmp_path, _metrics(tmp_path))
    snapshot = doc.read_text(encoding="utf-8")
    second = collect_metrics.write(tmp_path, _metrics(tmp_path))

    assert first  # the first run rewrote METRICS.json and the document
    assert second == []
    assert doc.read_text(encoding="utf-8") == snapshot


def test_optional_counts_are_carried_forward_not_nulled():
    fresh = {"counts": {"mcp_tools": 5, "python_tests": None, "native_tests": None}}
    previous = {"counts": {"mcp_tools": 4, "python_tests": 677, "native_tests": 182}}

    merged = collect_metrics.merge_optional_counts(fresh, previous)

    assert merged["counts"]["python_tests"] == 677
    assert merged["counts"]["native_tests"] == 182
    # A count derived from files is never carried over; the tree always wins.
    assert merged["counts"]["mcp_tools"] == 5


def test_uncomputable_counts_do_not_report_drift(tmp_path: Path):
    _build_tree(tmp_path)
    collect_metrics.write(tmp_path, _metrics(tmp_path))

    # python_tests/native_tests are None here (collection skipped) and must be
    # treated as "unknown", not as "changed to null".
    assert collect_metrics.check(tmp_path, _metrics(tmp_path)) == []
