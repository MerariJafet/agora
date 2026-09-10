"""Fail-closed verification of the complete local VM time evidence, without booting VMs."""

import argparse
import hashlib
import json
from pathlib import Path

PROFILES = {0, 60, -60, 300, -300, 1800, -1800}


def verify(directory):
    directory = Path(directory)
    result = json.loads((directory / "results.json").read_text())
    assert result["status"] == "PASS", "campaign did not pass"
    assert result["vm_count"] == 4 and result["host_clock_modified"] is False
    wall_elapsed = result["host_end_time"] - result["host_start_time"]
    monotonic_elapsed = result["host_monotonic_end"] - result["host_monotonic_start"]
    assert abs(wall_elapsed - monotonic_elapsed) < 3, "host clock discontinuity"
    rows = result["profiles"]
    assert len(rows) == 7 and {r["skew_seconds"] for r in rows} == PROFILES
    for row in rows:
        assert row["status"] == "PASS" and row["premature_maturation_rejected"] is True
        assert abs(row["observed_skew_seconds"] - row["skew_seconds"]) < 3
        assert row["observed_guest_clock"]["clock"] == "clock_gettime(CLOCK_REALTIME)"
        assert row["restart_height"] > row["consensus_height"]
        assert row["common_height"] >= row["partition_3_1_height"]
        assert len(row["app_hashes"]) == 4 and len(set(row["app_hashes"])) == 1
    assert result["post_finality_wall_clock_rewind"]["status"] == "PASS"
    assert result["partition_2_2_recovery"]["status"] == "PASS"
    matrix = json.loads((directory / "apphash-matrix.json").read_text())
    assert [r["height"] for r in matrix] == list(range(1, len(matrix) + 1))
    assert result["all_height_apphash_consistency"]["heights"] == len(matrix)
    for row in matrix:
        assert len(row["app_hashes"]) == 4 and len(set(row["app_hashes"])) == 1
        assert len(row["block_hashes"]) == 4 and len(set(row["block_hashes"])) == 1
    source_hash = hashlib.sha256((directory / "application-source.tar.gz").read_bytes()).hexdigest()
    assert source_hash == result["application_source_archive_sha256"]
    return {"status": "PASS", "profiles": len(rows), "compared_heights": len(matrix)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    print(json.dumps(verify(parser.parse_args().directory)))
