#!/usr/bin/env python3
"""Generate nine evidence datasets and eight SVG figures; never infer unreported success.

Input contracts: AGORA_V03_RUN_V1. Legacy monetary/chaos files are accepted ONLY
with --historical; their rows retain HISTORICAL_V02, never a V0.3 promotion.
No network calls, model calls, private traces, database mutations or secret reads.
"""

import argparse
import csv
import hashlib
import html
import json
import textwrap
import xml.etree.ElementTree as et
from pathlib import Path

SCHEMA = "AGORA_V03_RUN_V1"
AXES = (
    "consensus_correctness",
    "state_machine_correctness",
    "economic_correctness",
    "provenance_correctness",
    "scientific_protocol_correctness",
    "scientific_result_accuracy",
)
STATUSES = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}
TABLES = (
    "consensus_results",
    "apphash_consistency",
    "monetary_property_results",
    "failure_injection_results",
    "scientific_experiments",
)
FIGURES = (
    "agora_architecture",
    "scientific_state_machine",
    "tokoin_transaction_path",
    "four_validator_topology",
    "failure_recovery_timeline",
    "contribution_genealogy",
    "reward_derivation",
    "experiment_outcome_matrix",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric(value):
    if not isinstance(value, dict):
        return {"status": "UNKNOWN", "evidence": [], "reason": "No explicit metric assessment"}
    result = dict(value)
    result["status"] = value.get("status", "UNKNOWN")
    if result["status"] not in STATUSES:
        raise ValueError("Unknown metric status")
    if result["status"] in {"PASS", "FAIL"} and not value.get("evidence"):
        result = {
            "status": "UNKNOWN",
            "evidence": [],
            "reason": "Assessment lacks evidence references",
        }
    return result


def csv_write(path, rows):
    columns = ["run_id", "evidence_kind", "source", "source_sha256"]
    columns += sorted({key for row in rows for key in row} - set(columns))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def svg(path, title, lines, subtitle):
    # Static standalone SVG; lines derived from datasets or explicitly conceptual.
    lines = [part for line in lines for part in textwrap.wrap(str(line), width=140)]
    height = max(220, 115 + 30 * len(lines))
    content = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" '
        f'height="{height}" viewBox="0 0 1200 {height}">',
        '<rect width="100%" height="100%" fill="#fafafa"/>',
        f'<text x="24" y="35" font-family="sans-serif" font-size="22">{html.escape(title)}</text>',
        '<text x="24" y="64" font-family="sans-serif" font-size="13">'
        f"{html.escape(subtitle)}</text>",
    ]
    for index, line in enumerate(lines):
        content.append(
            f'<text x="24" y="{103 + 30 * index}" font-family="monospace" font-size="13">'
            f"{html.escape(str(line))}</text>"
        )
    path.write_text("\n".join([*content, "</svg>\n"]))


def graph_svg(path, title, labels, connections, subtitle):
    """Conceptual / observed directed graph with explicit provenance subtitle."""
    width = 1200
    columns = 3
    height = 135 + 115 * max(1, (len(labels) + columns - 1) // columns)
    positions = [(30 + (i % columns) * 390, 105 + (i // columns) * 115) for i in range(len(labels))]
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#fafafa"/>',
        '<defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" '
        'refY="4" orient="auto"><path d="M0,0 L10,4 L0,8" fill="#667"/></marker></defs>',
        f'<text x="24" y="35" font-family="sans-serif" font-size="22">{html.escape(title)}</text>',
        f'<text x="24" y="64" font-family="sans-serif" font-size="12">'
        f"{html.escape(subtitle)}</text>",
    ]
    for left, right in connections:
        x1, y1 = positions[left]
        x2, y2 = positions[right]
        pieces.append(
            f'<line x1="{x1 + 175}" y1="{y1 + 25}" x2="{x2 + 175}" '
            f'y2="{y2 + 25}" stroke="#667" marker-end="url(#arrow)"/>'
        )
    for label, (x, y) in zip(labels, positions, strict=True):
        pieces += [
            f'<rect x="{x}" y="{y}" width="350" height="55" rx="5" '
            'fill="#e8effa" stroke="#31547b"/>',
            f'<text x="{x + 12}" y="{y + 31}" font-family="sans-serif" '
            f'font-size="13">{html.escape(label)}</text>',
        ]
    path.write_text("\n".join([*pieces, "</svg>\n"]))


def outcome_svg(path, rows):
    """Measured categorical outcome matrix, no invented success counts."""
    if not rows:
        svg(
            path,
            "Experiment outcome matrix",
            ["UNKNOWN: no experiment measurements"],
            "Source: scientific_experiments.csv",
        )
        return
    height = 150 + len(rows) * 45
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}">',
        '<rect width="100%" height="100%" fill="#fafafa"/>',
        '<text x="24" y="35" font-family="sans-serif" font-size="22">'
        "Six independent correctness axes</text>",
    ]
    for col, label in enumerate(
        ["Consensus", "State", "Economy", "Provenance", "Procedure", "Accuracy"]
    ):
        pieces.append(
            f'<text x="{315 + col * 140}" y="85" font-family="sans-serif" '
            f'font-size="13">{label}</text>'
        )
    for i, row in enumerate(rows):
        y = 100 + 45 * i
        label = str(row.get("experiment_id", "UNKNOWN")) + " / " + row["evidence_kind"]
        pieces.append(
            f'<text x="24" y="{y + 22}" font-family="sans-serif" '
            f'font-size="12">{html.escape(label)}</text>'
        )
        for col, axis in enumerate(AXES):
            status = row[axis]["status"]
            color = {
                "PASS": "#cae8d5",
                "FAIL": "#f4cccc",
                "UNKNOWN": "#eee0bb",
                "NOT_APPLICABLE": "#ddd",
            }[status]
            x = 310 + 140 * col
            pieces.append(f'<rect x="{x}" y="{y}" width="132" height="32" fill="{color}"/>')
            pieces.append(
                f'<text x="{x + 4}" y="{y + 21}" font-family="sans-serif" '
                f'font-size="11">{status}</text>'
            )
    pieces.append("</svg>")
    path.write_text("\n".join(pieces) + "\n")


def generate(inputs, historical, output, junit=()):
    output.mkdir(parents=True, exist_ok=True)
    if (output / "PAPER_EVIDENCE_INDEX.json").exists():
        raise FileExistsError("Frozen evidence output exists; choose a new run directory")
    tables = {name: [] for name in TABLES}
    inventory, nodes, edges, rewards, limitations = [], [], [], [], []
    for path, history in [(p, False) for p in inputs] + [(p, True) for p in historical]:
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError(f"Run object required: {path}")
        schema = raw.get("schema_version", raw.get("schema"))
        if "schema_version" in raw and "schema" in raw and raw["schema_version"] != raw["schema"]:
            raise ValueError("Conflicting evidence schema aliases")
        kind = "HISTORICAL_V02" if history else "V03"
        base = {
            "run_id": raw.get("run_id", path.parent.name),
            "evidence_kind": kind,
            "source": str(path),
            "source_sha256": sha(path),
        }
        entry = {
            **base,
            "status": raw.get("status", "UNKNOWN"),
            "source_commit": raw.get("source_commit"),
            "schema_recognized": schema == SCHEMA,
        }
        inventory.append(entry)
        if schema == SCHEMA:
            for name in TABLES:
                for row in raw.get(name, []):
                    if not isinstance(row, dict):
                        raise ValueError(f"Object rows required: {name}")
                    item = {**row, **base}
                    if name == "scientific_experiments":
                        item.update({axis: metric(row.get(axis)) for axis in AXES})
                    tables[name].append(item)
            for key, destination in [
                ("contribution_nodes", nodes),
                ("contribution_edges", edges),
                ("reward_derivations", rewards),
                ("limitations", limitations),
            ]:
                for original in raw.get(key, []):
                    if key == "limitations" and isinstance(original, str):
                        row = {"status": "LIMITATION", "reason": original}
                    elif isinstance(original, dict):
                        row = dict(original)
                    else:
                        raise ValueError(f"Object rows required: {key}")
                    aliases = {
                        "contribution_edges": {"source": "source_node", "target": "target_node"},
                        "reward_derivations": {
                            "units": "total_units",
                            "tree_root": "contribution_tree_root",
                        },
                    }.get(key, {})
                    for alias, target in aliases.items():
                        if alias in row:
                            if target in row and row[target] != row[alias]:
                                raise ValueError(
                                    f"Conflicting evidence field aliases: {alias}/{target}"
                                )
                            row[target] = row[alias]
                    destination.append({**row, **base})
            if not raw.get("scientific_experiments") and raw.get("experiment_id"):
                tables["scientific_experiments"].append(
                    {
                        **base,
                        "experiment_id": raw["experiment_id"],
                        **{axis: metric(raw.get("metrics", {}).get(axis)) for axis in AXES},
                    }
                )
        elif history:
            if "counts" in raw and "requested_sequences" in raw:
                tables["monetary_property_results"].append(
                    {
                        **base,
                        **raw["counts"],
                        "status": "PASS"
                        if raw.get("pass") is True
                        else "FAIL"
                        if raw.get("pass") is False
                        else "UNKNOWN",
                        "seed": raw.get("seed"),
                        "corpus_sha256": raw.get("corpus_sha256"),
                    }
                )
            for scenario, result in raw.get("scenarios", {}).items():
                tables["consensus_results"].append({**base, "scenario": scenario, **result})
                tables["failure_injection_results"].append(
                    {
                        **base,
                        "scenario": scenario,
                        **result,
                        "timeline_status": "UNKNOWN_NO_ABSOLUTE_EVENT_TIMESTAMPS",
                    }
                )
            limitations.append(
                {
                    **base,
                    "status": "HISTORICAL_ONLY",
                    "reason": "V0.2 source is not V0.3 execution evidence",
                }
            )
        else:
            entry["status"] = "UNKNOWN"
            limitations.append(
                {
                    **base,
                    "status": "UNKNOWN",
                    "reason": "Unrecognized run schema; not promoted to PASS",
                }
            )
    for path in junit:
        if path.stat().st_size > 20_000_000:
            raise ValueError("JUnit input exceeds bounded size")
        xml = path.read_text(encoding="utf-8")
        if "\x00" in xml or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise ValueError("DTD/entities and non-UTF8 XML are not supported")
        tree = et.fromstring(xml)  # noqa: S314 - UTF8, bounded, DTD/entities rejected above
        for case in tree.findall(".//testcase"):
            status = "PASS"
            if case.find("failure") is not None or case.find("error") is not None:
                status = "FAIL"
            elif case.find("skipped") is not None:
                status = "NOT_APPLICABLE"
            inventory.append(
                {
                    "run_id": path.stem,
                    "evidence_kind": "V03_TEST_SUITE",
                    "source": str(path),
                    "source_sha256": sha(path),
                    "test_id": case.get("classname", "") + "::" + case.get("name", ""),
                    "status": status,
                    "seconds": case.get("time"),
                    "schema_recognized": True,
                }
            )
    for name, rows in tables.items():
        if not rows:
            limitations.append(
                {"dataset": name, "status": "UNKNOWN", "reason": "No measured rows supplied"}
            )
        csv_write(output / f"{name}.csv", rows)
    for filename, value in {
        "test_inventory.json": inventory,
        "agent_contribution_graph.json": {"nodes": nodes, "edges": edges},
        "reward_derivation.json": rewards,
        "limitations.json": limitations,
    }.items():
        (output / filename).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    figure_dir = output / "figures"
    figure_dir.mkdir(exist_ok=True)
    svg(
        figure_dir / "agora_architecture.svg",
        "AGORA architecture",
        [
            "AGORA identities / artifacts / scientific workflow",
            "                 | content hashes + signed protocol transactions",
            "TOKOIN deterministic application <-> CometBFT consensus",
            "                 | state root / immutable block order",
            "Read-only wallet / explorer / independent replay",
        ],
        "Conceptual architecture; diagram is not experimental proof",
    )
    svg(
        figure_dir / "scientific_state_machine.svg",
        "Scientific state machine",
        [
            "Challenge -> hypothesis -> contributions -> evidence -> experiment -> replication",
            "Blind review commit -> reveal -> decision -> challenge / appeal -> resolution",
            "Contribution tree frozen -> distribution -> signed reward -> LOCKED",
            "Protocol maturity and challenge resolution -> FINALIZED (separate from truth)",
        ],
        "Protocol design; observed transition coverage is in scientific_experiments.csv",
    )
    svg(
        figure_dir / "tokoin_transaction_path.svg",
        "TOKOIN transaction path",
        [
            "Domain-bound signed transaction -> broadcast -> CheckTx -> mempool",
            "CometBFT proposal / quorum -> FinalizeBlock -> Commit -> AppHash",
            "Independent node replay -> wallet query / provenance verification",
        ],
        "Conceptual transaction path; actual inclusion requires run evidence",
    )
    svg(
        figure_dir / "four_validator_topology.svg",
        "Four-validator topology",
        [
            "consensus_validator A <-> B <-> C <-> D (peer network)",
            "Each validator: CometBFT + deterministic ABCI application",
            "Epistemic reviewers are separate identities and responsibilities",
            "One PC with four processes or VMs is not four independent operators",
        ],
        "Target local topology, not evidence of external decentralization",
    )
    events = tables["failure_injection_results"]
    svg(
        figure_dir / "failure_recovery_timeline.svg",
        "Failure and recovery observations",
        [
            f"{r['run_id']}: {r.get('event_time', 'TIME UNKNOWN')} | "
            f"{r.get('scenario', r.get('event', 'UNKNOWN'))} | {r.get('status', 'UNKNOWN')}"
            for r in events
        ]
        or ["UNKNOWN: no measured event timeline supplied"],
        "Only supplied event times; missing timestamps are never synthesized",
    )
    svg(
        figure_dir / "contribution_genealogy.svg",
        "Contribution genealogy",
        [
            f"{n.get('node_id', n.get('id', 'UNKNOWN'))} | "
            f"author={n.get('agent_id', 'UNKNOWN')} | hash={n.get('content_hash', 'UNKNOWN')}"
            for n in nodes
        ]
        + [
            f"{e.get('source_node', 'UNKNOWN')} -> {e.get('target_node', 'UNKNOWN')} "
            f"({e.get('relation', 'UNKNOWN')})"
            for e in edges
        ]
        or ["UNKNOWN: no contribution graph supplied"],
        "Source: agent_contribution_graph.json; author claims require referenced identity evidence",
    )
    svg(
        figure_dir / "reward_derivation.svg",
        "Reward derivation",
        [
            f"{r.get('reward_id', 'UNKNOWN')} | total_units={r.get('total_units', 'UNKNOWN')} | "
            f"root={r.get('contribution_tree_root', 'UNKNOWN')}"
            for r in rewards
        ]
        or ["UNKNOWN: no measured reward derivation supplied"],
        "Source: reward_derivation.json; no hypothetical reward amount plotted",
    )
    svg(
        figure_dir / "experiment_outcome_matrix.svg",
        "Experiment outcome matrix",
        [
            "Columns: consensus | state machine | economy | provenance | "
            "scientific protocol | scientific accuracy",
            *[
                f"{r.get('experiment_id', 'UNKNOWN')} [{r['evidence_kind']}]: "
                + " | ".join(r[axis]["status"] for axis in AXES)
                for r in tables["scientific_experiments"]
            ],
        ]
        or ["UNKNOWN"],
        "Source: scientific_experiments.csv; six axes remain separate",
    )
    # Replace conceptual text views with explicit graphs; tables remain authoritative.
    for name, title, labels in [
        (
            "agora_architecture",
            "AGORA architecture",
            [
                "Agents / public artifacts",
                "Scientific protocol",
                "Signed hash commitments",
                "TOKOIN state machine",
                "CometBFT consensus",
                "Wallet / replay",
            ],
        ),
        (
            "scientific_state_machine",
            "Scientific state machine",
            [
                "Challenge / hypothesis",
                "Evidence / experiments",
                "Replication / critique",
                "Blind reviews / dispute",
                "Frozen tree / reward",
                "LOCKED / maturity",
            ],
        ),
        (
            "tokoin_transaction_path",
            "TOKOIN transaction path",
            [
                "Signed envelope",
                "Broadcast / CheckTx",
                "Proposal / consensus",
                "FinalizeBlock / Commit",
                "Canonical AppHash",
                "Query / replay",
            ],
        ),
    ]:
        graph_svg(
            figure_dir / f"{name}.svg",
            title,
            labels,
            [(i, i + 1) for i in range(len(labels) - 1)],
            "Conceptual design, not experimental proof; run tables establish observed coverage",
        )
    graph_svg(
        figure_dir / "four_validator_topology.svg",
        "Four-validator topology",
        ["Consensus A", "Consensus B", "Consensus C", "Consensus D"],
        [(i, j) for i in range(4) for j in range(i + 1, 4)],
        "Target peer topology; four processes or VMs on one PC are not independent operators",
    )
    outcome_svg(figure_dir / "experiment_outcome_matrix.svg", tables["scientific_experiments"])
    files = sorted(
        p for p in output.rglob("*") if p.is_file() and p.name != "PAPER_EVIDENCE_INDEX.json"
    )
    index = {
        "schema_version": "AGORA_PAPER_EVIDENCE_V1",
        "generator_sha256": sha(Path(__file__)),
        "inputs": inventory,
        "datasets": 9,
        "figures": 8,
        "files": [
            {"path": str(p.relative_to(output)), "sha256": sha(p), "bytes": p.stat().st_size}
            for p in files
        ],
        "promotion_decision": "NOT_AUTOMATICALLY_GRANTED",
    }
    (output / "PAPER_EVIDENCE_INDEX.json").write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n"
    )
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--historical", type=Path, action="append", default=[])
    parser.add_argument("--junit", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(generate(args.input, args.historical, args.output, args.junit), sort_keys=True)
    )


if __name__ == "__main__":
    main()
