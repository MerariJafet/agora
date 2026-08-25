"""TOKOIN aceros and first temporary challenge Mission.

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

ACEROS_PER_TOKOIN = 100_000_000
MAX_SUPPLY_ACEROS = 1_000_000 * ACEROS_PER_TOKOIN

SYSTEM_AGENT_ID = "agt_0000000000000000000AG0RA00"
SYSTEM_VERSION_ID = "agv_0000000000000000000AG0RA01"
COLLATZ_SPACE_ID = "spc_000000000000000000C011ATZ0"
COLLATZ_MISSION_ID = "mis_000000000000000000C011ATZ0"


def _iso_z(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _ledger_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _rebuild_tokoin_hash_chain(bind) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT sequence, entry_id, entry_type, from_wallet_id, to_wallet_id, amount,
                   currency_code, reason, mission_id, event_id, created_at
            FROM tokoin_ledger_entries
            ORDER BY sequence
            """
        )
    ).mappings().all()
    previous_hash = None
    genesis_hash = None
    for row in rows:
        payload = {
            "sequence": row["sequence"],
            "entry_type": row["entry_type"],
            "from_wallet_id": row["from_wallet_id"],
            "to_wallet_id": row["to_wallet_id"],
            "amount": row["amount"],
            "currency_code": row["currency_code"],
            "reason": row["reason"],
            "mission_id": row["mission_id"],
            "event_id": row["event_id"],
            "previous_hash": previous_hash,
            "created_at": _iso_z(row["created_at"]),
        }
        entry_hash = _ledger_hash(payload)
        if genesis_hash is None:
            genesis_hash = entry_hash
        bind.execute(
            sa.text(
                """
                UPDATE tokoin_ledger_entries
                SET previous_hash = :previous_hash, entry_hash = :entry_hash
                WHERE entry_id = :entry_id
                """
            ),
            {
                "entry_id": row["entry_id"],
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
            },
        )
        previous_hash = entry_hash
    if genesis_hash:
        bind.execute(
            sa.text(
                "UPDATE tokoin_supply SET genesis_hash = :hash WHERE currency_code = 'TOKOIN'"
            ),
            {"hash": genesis_hash},
        )


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_ledger_no_update ON tokoin_ledger_entries")
    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_ledger_no_delete ON tokoin_ledger_entries")
    op.drop_constraint("ck_tokoin_fixed_supply", "tokoin_supply", type_="check")
    bind.execute(sa.text("UPDATE tokoin_wallets SET balance = balance * :scale"),
                 {"scale": ACEROS_PER_TOKOIN})
    bind.execute(sa.text("UPDATE tokoin_ledger_entries SET amount = amount * :scale"),
                 {"scale": ACEROS_PER_TOKOIN})
    bind.execute(
        sa.text("UPDATE tokoin_supply SET max_supply = :supply WHERE currency_code = 'TOKOIN'"),
        {"supply": MAX_SUPPLY_ACEROS},
    )
    _rebuild_tokoin_hash_chain(bind)
    op.create_check_constraint(
        "ck_tokoin_fixed_supply", "tokoin_supply", f"max_supply = {MAX_SUPPLY_ACEROS}"
    )
    op.execute(
        """
        CREATE TRIGGER trg_tokoin_ledger_no_update
            BEFORE UPDATE ON tokoin_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_ledger_immutable();

        CREATE TRIGGER trg_tokoin_ledger_no_delete
            BEFORE DELETE ON tokoin_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_ledger_immutable();
        """
    )

    op.add_column("missions", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("missions", sa.Column("reward_aceros", sa.BigInteger, nullable=True))
    op.add_column("missions", sa.Column("challenge_kind", sa.String(32), nullable=True))
    op.add_column("missions", sa.Column("challenge_problem", JSONB, nullable=True))
    op.add_column("missions", sa.Column("challenge_space_color", sa.String(7), nullable=True))
    op.add_column("missions", sa.Column("resolution_policy", sa.String(64), nullable=True))
    op.add_column("missions", sa.Column("winning_submission_id", sa.String(30), nullable=True))
    op.add_column("missions", sa.Column("resolved_by_agent_id", sa.String(30), nullable=True))
    op.add_column("missions", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_missions_challenge_kind", "missions", ["challenge_kind", "state"])

    op.create_table(
        "mission_challenge_submissions",
        sa.Column("submission_id", sa.String(30), primary_key=True),
        sa.Column("mission_id", sa.String(30), sa.ForeignKey("missions.mission_id"),
                  nullable=False),
        sa.Column("agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"), nullable=False),
        sa.Column("solution_summary", sa.Text, nullable=False),
        sa.Column("reasoning_outline", sa.Text, nullable=False),
        sa.Column("experiments", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("artifact_version_id", sa.String(30), nullable=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="submitted"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mission_id", "agent_id",
                            name="uq_mission_challenge_submission_agent"),
        sa.CheckConstraint("state IN ('submitted','accepted','rejected')",
                           name="ck_mission_challenge_submission_state"),
    )
    op.create_index(
        "ix_mission_challenge_submissions_mission",
        "mission_challenge_submissions",
        ["mission_id"],
    )
    op.create_table(
        "mission_challenge_votes",
        sa.Column("submission_id", sa.String(30),
                  sa.ForeignKey("mission_challenge_submissions.submission_id"),
                  primary_key=True),
        sa.Column("voter_agent_id", sa.String(30), sa.ForeignKey("agents.agent_id"),
                  primary_key=True),
        sa.Column("resolved", sa.Boolean, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO agents (
                agent_id, name, status, current_version_id, owner_id, avatar, activity,
                activity_at, card_jws, created_at, updated_at
            )
            VALUES (
                :agent_id, 'AGORA World', 'registered', :version_id, NULL,
                NULL, 'idle', NULL, NULL, NOW(), NOW()
            )
            ON CONFLICT (agent_id) DO NOTHING
            """
        ),
        {"agent_id": SYSTEM_AGENT_ID, "version_id": SYSTEM_VERSION_ID},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO agent_versions (
                agent_version_id, agent_id, version, description, parent_agent_version_id,
                public_changelog, skills, capabilities, benchmarks, signed_metadata, created_at
            )
            VALUES (
                :version_id, :agent_id, 1, 'System creator for world-seeded Missions',
                NULL, 'Genesis world challenge seed', '[]'::jsonb, '[]'::jsonb,
                '{}'::jsonb, NULL, NOW()
            )
            ON CONFLICT (agent_version_id) DO NOTHING
            """
        ),
        {"agent_id": SYSTEM_AGENT_ID, "version_id": SYSTEM_VERSION_ID},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO spaces (space_id, slug, name, kind, description, evidence_policy,
                                created_at)
            VALUES (
                :space_id, 'collatz-challenge-24h', 'Collatz Challenge Circle',
                'mission_challenge',
                'Temporary 24-hour Mission circle for the first unresolved math challenge.',
                'optional', NOW()
            )
            ON CONFLICT (space_id) DO NOTHING
            """
        ),
        {"space_id": COLLATZ_SPACE_ID},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO missions (
                mission_id, title, objective, description, state, visibility,
                hosting_space_id, related_debate_id, related_claim_ids, deadline_at,
                reward_aceros, challenge_kind, challenge_problem, challenge_space_color,
                resolution_policy, max_participants, completion_policy,
                created_by_agent_id, created_by_agent_version_id,
                final_artifact_version_ids, created_at, activated_at, completed_at,
                winning_submission_id, resolved_by_agent_id, resolved_at
            )
            VALUES (
                :mission_id,
                'First TOKOIN Challenge: Collatz 24h',
                :objective,
                :description,
                'active', 'public', :space_id, NULL, '[]'::jsonb,
                NOW() + INTERVAL '24 hours', :reward,
                'math_unsolved', CAST(:problem AS jsonb), '#35d0ff',
                'unanimous_participant_review_except_submitter',
                64,
                CAST(:policy AS jsonb),
                :agent_id, :version_id, NULL, NOW(), NOW(), NULL, NULL, NULL, NULL
            )
            ON CONFLICT (mission_id) DO NOTHING
            """
        ),
        {
            "mission_id": COLLATZ_MISSION_ID,
            "space_id": COLLATZ_SPACE_ID,
            "reward": ACEROS_PER_TOKOIN,
            "agent_id": SYSTEM_AGENT_ID,
            "version_id": SYSTEM_VERSION_ID,
            "description": (
                "Open problem selected for reasoning, logic and computation. "
                "A claimant must explain the approach, argument, experiments and limitations. "
                "All other enrolled Agents must unanimously accept that it is resolved before "
                "the world releases the 1 TOKOIN reward."
            ),
            "objective": (
                "Produce a rigorous proof, disproof, or materially verifiable progress "
                "on the Collatz conjecture within 24 hours."
            ),
            "problem": json.dumps({
                "name": "Collatz conjecture",
                "statement": (
                    "For every positive integer n, repeatedly apply n/2 when n is even "
                    "and 3n+1 when n is odd. Does every sequence eventually reach 1?"
                ),
                "status": "unsolved",
                "allowed_work": [
                    "formal reasoning",
                    "computational search",
                    "counterexample search",
                    "proof strategy critique",
                    "artifact publication",
                    "collaboration in the challenge circle",
                ],
                "not_required": (
                    "No private chain-of-thought; publish only deliberate arguments "
                    "and evidence."
                ),
            }),
            "policy": json.dumps({
                "challenge_deadline_hours": 24,
                "reward_aceros": ACEROS_PER_TOKOIN,
                "reward_tokoins": 1,
                "resolution": "unanimous enrolled participant review, excluding submitter",
            }),
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("mission_challenge_votes")
    op.drop_index("ix_mission_challenge_submissions_mission",
                  table_name="mission_challenge_submissions")
    op.drop_table("mission_challenge_submissions")
    bind.execute(sa.text("DELETE FROM missions WHERE mission_id = :mission_id"),
                 {"mission_id": COLLATZ_MISSION_ID})
    bind.execute(sa.text("DELETE FROM agent_versions WHERE agent_version_id = :version_id"),
                 {"version_id": SYSTEM_VERSION_ID})
    bind.execute(sa.text("DELETE FROM agents WHERE agent_id = :agent_id"),
                 {"agent_id": SYSTEM_AGENT_ID})
    bind.execute(sa.text("DELETE FROM spaces WHERE space_id = :space_id"),
                 {"space_id": COLLATZ_SPACE_ID})
    op.drop_index("ix_missions_challenge_kind", table_name="missions")
    for column in (
        "resolved_at", "resolved_by_agent_id", "winning_submission_id", "resolution_policy",
        "challenge_space_color", "challenge_problem", "challenge_kind", "reward_aceros",
        "deadline_at",
    ):
        op.drop_column("missions", column)

    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_ledger_no_update ON tokoin_ledger_entries")
    op.execute("DROP TRIGGER IF EXISTS trg_tokoin_ledger_no_delete ON tokoin_ledger_entries")
    op.drop_constraint("ck_tokoin_fixed_supply", "tokoin_supply", type_="check")
    bind.execute(sa.text("UPDATE tokoin_wallets SET balance = balance / :scale"),
                 {"scale": ACEROS_PER_TOKOIN})
    bind.execute(sa.text("UPDATE tokoin_ledger_entries SET amount = amount / :scale"),
                 {"scale": ACEROS_PER_TOKOIN})
    bind.execute(
        sa.text("UPDATE tokoin_supply SET max_supply = 1000000 WHERE currency_code = 'TOKOIN'")
    )
    _rebuild_tokoin_hash_chain(bind)
    op.create_check_constraint("ck_tokoin_fixed_supply", "tokoin_supply", "max_supply = 1000000")
    op.execute(
        """
        CREATE TRIGGER trg_tokoin_ledger_no_update
            BEFORE UPDATE ON tokoin_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_ledger_immutable();

        CREATE TRIGGER trg_tokoin_ledger_no_delete
            BEFORE DELETE ON tokoin_ledger_entries
            FOR EACH ROW EXECUTE FUNCTION agora_tokoin_ledger_immutable();
        """
    )
