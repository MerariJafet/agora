"""Offline regressions for the finite tool boundary; never invoke providers."""

import copy

import pytest

from scripts.v03_llm_campaign import compute, hash_object
from scripts.v03_llm_evaluate import verify_tools


@pytest.mark.parametrize(
    "method,count", [("trial_division", 25), ("sieve", 25), ("exclusive_upper", 24)]
)
def test_calculator_preserves_boundary(method, count):
    value = compute(
        {
            "experiment_id": "LLM-SCI-004",
            "tool": "prime_count",
            "low": 2,
            "high": 97,
            "method": method,
        }
    )
    assert value["result"]["count"] == count


@pytest.mark.parametrize(
    "low,high", [(0, 10001), (-1, 97), (98, 97), (True, 97), (0, None), (0, 1.5)]
)
def test_model_tool_parameters_fail_closed(low, high):
    with pytest.raises(ValueError):
        compute(
            {
                "experiment_id": "LLM-SCI-001",
                "tool": "prime_count",
                "low": low,
                "high": high,
                "method": "sieve",
            }
        )


@pytest.mark.parametrize("tool", ["exec", "read_file", "http_get", "__import__"])
def test_arbitrary_tools_forbidden(tool):
    with pytest.raises(ValueError):
        compute(
            {"experiment_id": "LLM-SCI-001", "tool": tool, "low": 2, "high": 97, "method": "sieve"}
        )


def test_tampered_artifact_cannot_replay():
    artifact = compute(
        {
            "experiment_id": "LLM-SCI-001",
            "tool": "prime_count",
            "low": 2,
            "high": 97,
            "method": "sieve",
        }
    )
    report = {"tool_artifacts": [artifact]}
    report["content_hash"] = hash_object(report)
    campaign = {"agents": {"researcher": report}}
    assert verify_tools(campaign) == 1
    changed = copy.deepcopy(campaign)
    changed["agents"]["researcher"]["tool_artifacts"][0]["result"]["count"] = 100
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_tools(changed)


async def test_scientific_challenge_creation_requires_identity(api_client):
    response = await api_client.post(
        "/v1/research-protocol/test-challenges",
        json={
            "title": "Unauthorized TEST challenge",
            "objective": "Cannot create anonymously",
            "description": "No LLM call",
            "experiment_id": "LLM-SCI-001",
            "parameters": {},
        },
    )
    assert response.status_code == 401


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_large_public_package_uses_stdin(provider, monkeypatch, tmp_path):
    import json
    import subprocess
    from pathlib import Path

    from scripts.v03_llm_campaign import invoke

    prompt = "Public reproducibility package " + "x" * 200_000
    output = {"actions": [], "contributions": []}

    def fake_process(command, **kwargs):
        assert kwargs["input"] == prompt
        assert prompt not in command
        if provider == "codex":
            Path(command[command.index("-o") + 1]).write_text(json.dumps(output))
        return subprocess.CompletedProcess(
            command, 0, json.dumps({"structured_output": output}), "private diagnostics withheld"
        )

    monkeypatch.setattr(subprocess, "run", fake_process)
    assert invoke(provider, prompt, tmp_path / provider) == output
    receipt = (tmp_path / provider / "receipt.json").read_text()
    assert "private diagnostics" not in receipt
