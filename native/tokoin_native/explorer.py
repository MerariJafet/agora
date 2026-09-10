"""Offline explorer of replay-verified node state; no remote assets/scripts."""

import html
import json

from .core import MATURITY, UNIT, metrics


def render(store):
    state = store.state
    info = metrics(state)

    def amount(units):
        return f"{units // UNIT:,}.{units % UNIT:08d}"

    def table(headers, rows):
        return (
            "<table><thead><tr>"
            + "".join("<th>" + html.escape(h) + "</th>" for h in headers)
            + ("</tr></thead><tbody>")
            + "".join(
                "<tr>" + "".join("<td>" + html.escape(str(c)) + "</td>" for c in row) + "</tr>"
                for row in rows
            )
            + "</tbody></table>"
        )

    rewards = []
    for rid, r in state["rewards"].items():
        remaining = max(
            0,
            MATURITY
            - r["elapsed"]
            - (state["time"] - r["last_started"] if r["status"] == "LOCKED" else 0),
        )
        rewards.append(
            [
                rid,
                r["authorization"]["research_id"],
                r["status"],
                r.get("scientific_status", "VALID"),
                r.get("unlock_at"),
                json.dumps(r.get("scientific_invalidations", []), sort_keys=True),
                amount(r["authorization"]["reward_total"]),
                remaining,
                r["authorization"]["genealogy_root"],
            ]
        )
    blocks = store.export()["blocks"]
    return (
        """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TOKOIN · Explorador TEST</title><style>
body{font:16px system-ui;margin:32px;background:#101723;color:#e4ebf4}h1{color:#79ded0}
a{color:#79ded0}table{border-collapse:collapse;width:100%;font-size:13px;margin:16px 0}
td,th{text-align:left;border-bottom:1px solid #354355;padding:12px;overflow-wrap:anywhere}
section{overflow:auto;margin:28px 0;padding:20px;background:#192433;border-radius:12px}
.notice{background:#4b361b;padding:16px;border-radius:8px}pre{white-space:pre-wrap}</style>
<h1>TOKOIN · Explorador nativo TEST</h1><p class="notice">Instantánea local reproducida
 desde génesis. Sin reconocimiento económico. Este journal no sustituye la verificación
 de firmas del consenso CometBFT. No es una wallet conectada a producción.</p>"""
        + (
            "<section><h2>Suministro</h2>"
            + table(
                ["Magnitud", "TOKOIN"],
                [
                    [k, amount(info[k])]
                    for k in (
                        "created_units",
                        "circulating_units",
                        "locked_units",
                        "revoked_units",
                        "remaining_units",
                        "pilot_remaining_units",
                    )
                ],
            )
            + "</section>"
        )
        + (
            "<section><h2>Recompensas y procedencia</h2>"
            + table(
                [
                    "Reward",
                    "Investigación",
                    "Estado monetario",
                    "Estado científico",
                    "Unlock (tiempo cadena)",
                    "Invalidaciones posteriores",
                    "TOKOIN",
                    "Segundos pendientes",
                    "Genealogía",
                ],
                rewards,
            )
            + "</section>"
        )
        + (
            "<section><h2>Balances transferibles</h2>"
            + table(
                ["Dirección", "TOKOIN"],
                [[k, amount(v)] for k, v in sorted(state["balances"].items())],
            )
            + "</section>"
        )
        + (
            "<section><h2>Bloques de aplicación</h2>"
            + table(
                ["Altura", "Tiempo de cadena", "Transacciones", "State root", "Research root"],
                [
                    [
                        b["height"],
                        b["timestamp"],
                        len(b["transactions"]),
                        b["state_root"],
                        b["research_commitment_root"],
                    ]
                    for b in blocks
                ],
            )
            + "</section>"
        )
        + (
            "<section><h2>Transacciones firmadas</h2><pre>"
            + html.escape(
                json.dumps(
                    [
                        {"height": b["height"], "transactions": b["transactions"]}
                        for b in blocks
                        if b["transactions"]
                    ],
                    indent=2,
                )
            )
            + "</pre></section></html>"
        )
    )
