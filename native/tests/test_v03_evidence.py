"""Evidence must distinguish absence, failure, historical scope and independent axes."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "v03_evidence", Path(__file__).parents[1] / "tools/v03_evidence.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
AXES, generate = module.AXES, module.generate


def test_empty_is_unknown_and_has_all_required_outputs(tmp_path):
    index = generate([], [], tmp_path)
    assert index["datasets"] == 9
    assert len(list((tmp_path / "figures").glob("*.svg"))) == 8
    assert all(
        r["status"] == "UNKNOWN" for r in json.loads((tmp_path / "limitations.json").read_text())
    )
    assert index["promotion_decision"] != "PASS"


def test_axes_remain_separate_and_deterministic(tmp_path):
    run = tmp_path / "run.json"
    row = {axis: {"status": "PASS", "evidence": ["trace.json"]} for axis in AXES}
    row["scientific_result_accuracy"]["status"] = "FAIL"
    run.write_text(
        json.dumps(
            {
                "schema_version": "AGORA_V03_RUN_V1",
                "run_id": "test",
                "scientific_experiments": [{"experiment_id": "SCI", **row}],
            }
        )
    )
    first = generate([run], [], tmp_path / "one")
    second = generate([run], [], tmp_path / "two")
    assert first == second
    assert "FAIL" in (tmp_path / "one/scientific_experiments.csv").read_text()
    assert "PASS" in (tmp_path / "one/scientific_experiments.csv").read_text()


def test_missing_proof_and_unrecognized_schema_never_pass(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"status": "PASS"}))
    generate([run], [], tmp_path / "out")
    assert json.loads((tmp_path / "out/test_inventory.json").read_text())[0]["status"] == "UNKNOWN"
    run.write_text(
        json.dumps(
            {
                "schema_version": "AGORA_V03_RUN_V1",
                "experiment_id": "test",
                "metrics": {"consensus_correctness": {"status": "PASS"}},
            }
        )
    )
    generate([run], [], tmp_path / "other")
    assert "PASS" not in (tmp_path / "other/scientific_experiments.csv").read_text()


def test_historical_failure_preserved(tmp_path):
    run = tmp_path / "v02.json"
    run.write_text(json.dumps({"scenarios": {"test": {"status": "FAIL", "seconds": 3}}}))
    generate([], [run], tmp_path / "out")
    text = (tmp_path / "out/consensus_results.csv").read_text()
    assert "HISTORICAL_V02" in text and "FAIL" in text


def test_invalid_schema_rows_rejected(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"schema_version": "AGORA_V03_RUN_V1", "consensus_results": [1]}))
    with pytest.raises(ValueError):
        generate([run], [], tmp_path / "out")


def test_refuses_to_overwrite_frozen_evidence(tmp_path):
    generate([], [], tmp_path)
    with pytest.raises(FileExistsError):
        generate([], [], tmp_path)


def test_svg_is_well_formed_and_escapes_labels(tmp_path):
    import xml.etree.ElementTree as et

    module.svg(tmp_path / "test.svg", "<unsafe>", ["a & b"], "source")
    et.parse(tmp_path / "test.svg")  # noqa: S314 - locally generated constant test SVG
    assert "&lt;unsafe&gt;" in (tmp_path / "test.svg").read_text()


def test_junit_preserves_failures_and_skips(tmp_path):
    path = tmp_path / "tests.xml"
    path.write_text(
        '<testsuites><testsuite><testcase name="ok"/>'
        '<testcase name="bad"><failure>observed</failure></testcase>'
        '<testcase name="skip"><skipped/></testcase></testsuite></testsuites>'
    )
    generate([], [], tmp_path / "out", [path])
    inventory = json.loads((tmp_path / "out/test_inventory.json").read_text())
    assert [row["status"] for row in inventory] == ["PASS", "FAIL", "NOT_APPLICABLE"]


def test_junit_rejects_entity_expansion(tmp_path):
    path = tmp_path / "bad.xml"
    path.write_text('<!DOCTYPE test [<!ENTITY x "bad">]><testsuite/>')
    with pytest.raises(ValueError, match="DTD"):
        generate([], [], tmp_path / "out", [path])


def test_producer_aliases_normalize_without_inventing_measurements(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(
        json.dumps(
            {
                "schema": "AGORA_V03_RUN_V1",
                "run_id": "alias-fixture",
                "status": "PASS",
                "scientific_experiments": [{"experiment_id": "fixture"}],
                "contribution_edges": [{"source": "a", "target": "b", "relation": "uses"}],
                "reward_derivations": [{"reward_id": "r", "units": 20, "tree_root": "a" * 64}],
                "limitations": ["One operator", {"status": "UNKNOWN", "reason": "unmeasured"}],
            }
        )
    )
    out = tmp_path / "out"
    generate([run], [], out)
    inventory = json.loads((out / "test_inventory.json").read_text())
    assert inventory[0]["schema_recognized"] is True
    edge = json.loads((out / "agent_contribution_graph.json").read_text())["edges"][0]
    assert (edge["source_node"], edge["target_node"]) == ("a", "b")
    reward = json.loads((out / "reward_derivation.json").read_text())[0]
    assert reward["total_units"] == 20 and reward["contribution_tree_root"] == "a" * 64
    limits = json.loads((out / "limitations.json").read_text())
    assert limits[0]["reason"] == "One operator" and limits[0]["status"] == "LIMITATION"
    assert "PASS" not in (out / "scientific_experiments.csv").read_text()
    assert (out / "scientific_experiments.csv").read_text().count("UNKNOWN") >= len(AXES)


@pytest.mark.parametrize(
    "row",
    [
        {"schema": "bad", "schema_version": "AGORA_V03_RUN_V1"},
        {"schema": "AGORA_V03_RUN_V1", "reward_derivations": [{"units": 1, "total_units": 2}]},
        {"schema": "AGORA_V03_RUN_V1", "contribution_edges": [{"source": "a", "source_node": "b"}]},
    ],
)
def test_conflicting_aliases_rejected(tmp_path, row):
    run = tmp_path / "run.json"
    run.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="Conflicting"):
        generate([run], [], tmp_path / "out")
