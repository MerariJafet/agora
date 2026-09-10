"""Evidence gates reject fabricated coverage, mismatched roots and missing clock evidence."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

path = Path(__file__).parents[1] / "tools/v03_vm_verify.py"
spec = importlib.util.spec_from_file_location("vm_verify", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(tmp_path):
    source = b"TEST source archive fixture"
    (tmp_path / "application-source.tar.gz").write_bytes(source)
    row = {
        "status": "PASS",
        "premature_maturation_rejected": True,
        "observed_guest_clock": {"clock": "clock_gettime(CLOCK_REALTIME)"},
        "consensus_height": 2,
        "restart_height": 3,
        "partition_3_1_height": 4,
        "common_height": 5,
        "app_hashes": ["a"] * 4,
    }
    result = {
        "status": "PASS",
        "vm_count": 4,
        "host_clock_modified": False,
        "host_start_time": 10000,
        "host_end_time": 10100,
        "host_monotonic_start": 100,
        "host_monotonic_end": 200,
        "profiles": [
            dict(row, skew_seconds=s, observed_skew_seconds=s) for s in sorted(module.PROFILES)
        ],
        "post_finality_wall_clock_rewind": {"status": "PASS"},
        "partition_2_2_recovery": {"status": "PASS"},
        "all_height_apphash_consistency": {"heights": 1},
        "application_source_archive_sha256": hashlib.sha256(source).hexdigest(),
    }
    matrix = [{"height": 1, "app_hashes": ["a"] * 4, "block_hashes": ["b"] * 4}]
    return result, matrix


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "missing_profile",
        "missing_clock",
        "unchanged_clock",
        "divergence",
        "source_tamper",
        "missing_height",
        "no_restart",
        "early_maturity",
        "host_clock_changed",
    ],
)
def test_vm_evidence_fail_closed(tmp_path, fault):
    result, matrix = copy.deepcopy(fixture(tmp_path))
    if fault == "missing_profile":
        result["profiles"].pop()
    elif fault == "missing_clock":
        result["profiles"][0].pop("observed_guest_clock")
    elif fault == "unchanged_clock":
        result["profiles"][0]["observed_skew_seconds"] = 0
    elif fault == "divergence":
        matrix[0]["app_hashes"][2] = "wrong"
    elif fault == "source_tamper":
        (tmp_path / "application-source.tar.gz").write_bytes(b"changed")
    elif fault == "missing_height":
        matrix[0]["height"] = 2
    elif fault == "no_restart":
        result["profiles"][0]["restart_height"] = 1
    elif fault == "host_clock_changed":
        result["host_end_time"] += 60
    elif fault == "early_maturity":
        result["profiles"][0]["premature_maturation_rejected"] = False
    (tmp_path / "results.json").write_text(json.dumps(result))
    (tmp_path / "apphash-matrix.json").write_text(json.dumps(matrix))
    if fault == "none":
        assert module.verify(tmp_path)["status"] == "PASS"
    else:
        with pytest.raises((AssertionError, KeyError)):
            module.verify(tmp_path)


def test_guest_supervisor_refuses_host_execution(monkeypatch):
    guest_path = Path(__file__).parents[1] / "tools/v03_vm_guest.py"
    guest_spec = importlib.util.spec_from_file_location("vm_guest", guest_path)
    guest = importlib.util.module_from_spec(guest_spec)
    guest_spec.loader.exec_module(guest)
    monkeypatch.setattr(guest.os, "getpid", lambda: 9999)
    with pytest.raises(RuntimeError, match="requires PID 1"):
        guest.main()
