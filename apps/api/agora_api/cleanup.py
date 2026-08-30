"""Bounded ephemeral-data lifecycle (S1.1-T06).

Purges ONLY ephemeral operational rows:
- expired registration challenges (after a grace period),
- expired device sessions,
- outbox rows already published, older than the retention window.

The canonical `events` ledger is NEVER touched — there is no DELETE against
it anywhere in this module, and the DB triggers from migration 0001 would
reject one anyway (defense in depth).

Run manually or via cron:  .venv/bin/python -m agora_api.cleanup
(also `make cleanup`).
"""

import asyncio
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.db import dispose_engine, session_factory
from agora_api.events import now_utc
from agora_api.logging import configure_logging, get_logger
from agora_api.mission_challenges_service import expire_due_challenges
from agora_api.models import DeviceSession, EventOutbox, RegistrationChallenge

log = get_logger("agora.api.cleanup")

CHALLENGE_GRACE = timedelta(hours=1)
SESSION_GRACE = timedelta(hours=1)
OUTBOX_RETENTION = timedelta(days=7)


async def purge_expired_challenges(
    session: AsyncSession, grace: timedelta = CHALLENGE_GRACE
) -> int:
    """Deletes challenges whose expiry passed more than `grace` ago.
    Active/unexpired challenges are structurally out of range."""
    cutoff = now_utc() - grace
    result = await session.execute(
        delete(RegistrationChallenge).where(RegistrationChallenge.expires_at < cutoff)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def purge_expired_sessions(session: AsyncSession, grace: timedelta = SESSION_GRACE) -> int:
    cutoff = now_utc() - grace
    result = await session.execute(
        delete(DeviceSession).where(DeviceSession.expires_at < cutoff)
    )
    return int(getattr(result, "rowcount", 0) or 0)


async def purge_published_outbox(
    session: AsyncSession, retention: timedelta = OUTBOX_RETENTION
) -> int:
    """Outbox rows are delivery bookkeeping, not history: once published and
    past retention they are safe to drop. The event itself lives forever in
    the ledger."""
    cutoff = now_utc() - retention
    result = await session.execute(
        delete(EventOutbox).where(
            EventOutbox.published.is_(True), EventOutbox.published_at < cutoff
        )
    )
    return int(getattr(result, "rowcount", 0) or 0)


CLEANUP_ADVISORY_LOCK = 0xA60_A_C1EA  # arbitrary stable id for pg_try_advisory_lock


async def run_cleanup() -> dict[str, int]:
    """Redundancy-safe: a Postgres advisory lock guarantees only one logical
    cleanup execution even if cron/systemd/humans invoke it concurrently.
    The canonical Event Ledger is never touched (see module docstring)."""
    from sqlalchemy import text

    async with session_factory()() as session:
        locked = (
            await session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": CLEANUP_ADVISORY_LOCK},
            )
        ).scalar_one()
        if not locked:
            log.info("cleanup.skipped_already_running")
            return {"skipped": 1}
        try:
            counts = {
                "challenges_purged": await purge_expired_challenges(session),
                "sessions_purged": await purge_expired_sessions(session),
                "outbox_purged": await purge_published_outbox(session),
                "mission_challenge_deadlines_elapsed": await expire_due_challenges(session),
            }
            await session.commit()
        finally:
            await session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": CLEANUP_ADVISORY_LOCK},
            )
    log.info("cleanup.completed", **counts)
    return counts


def main() -> None:
    configure_logging()
    counts = asyncio.run(_main_async())
    print(counts)


async def _main_async() -> dict[str, int]:
    try:
        return await run_cleanup()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    main()
