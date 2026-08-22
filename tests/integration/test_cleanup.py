"""Ephemeral-data lifecycle (S1.1-T06): cleanup purges only expired/served
rows and can never touch the canonical Event Ledger."""

import secrets
from datetime import timedelta

import pytest
from agora_api.cleanup import (
    purge_expired_challenges,
    purge_expired_sessions,
    purge_published_outbox,
)
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_challenge_id
from agora_api.models import Event, EventOutbox, RegistrationChallenge
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


def _challenge(expires_delta: timedelta) -> RegistrationChallenge:
    return RegistrationChallenge(
        challenge_id=new_challenge_id(),
        nonce=secrets.token_urlsafe(32)[:43],
        public_key="A" * 43,
        agent_name=f"CleanupProbe-{secrets.token_hex(4)}",
        expires_at=now_utc() + expires_delta,
        consumed_at=None,
        created_at=now_utc(),
    )


async def test_active_challenges_survive_cleanup():
    async with session_factory()() as session:
        active = _challenge(timedelta(minutes=5))          # unexpired
        recent = _challenge(-timedelta(minutes=10))        # expired, within grace
        stale = _challenge(-timedelta(hours=3))            # expired past grace
        session.add_all([active, recent, stale])
        await session.commit()

        purged = await purge_expired_challenges(session, grace=timedelta(hours=1))
        await session.commit()
        assert purged >= 1

        remaining = {
            c.challenge_id
            for c in (
                (
                    await session.execute(
                        select(RegistrationChallenge).where(
                            RegistrationChallenge.challenge_id.in_(
                                [active.challenge_id, recent.challenge_id, stale.challenge_id]
                            )
                        )
                    )
                ).scalars()
            )
        }
        assert active.challenge_id in remaining
        assert recent.challenge_id in remaining  # inside grace window
        assert stale.challenge_id not in remaining


async def test_cleanup_never_touches_event_ledger():
    async with session_factory()() as session:
        before = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
        await purge_expired_challenges(session)
        await purge_expired_sessions(session)
        # retention=0 → maximally aggressive outbox purge of published rows
        await purge_published_outbox(session, retention=timedelta(seconds=0))
        await session.commit()
        after = (await session.execute(select(func.count()).select_from(Event))).scalar_one()
        assert after == before


async def test_outbox_purge_keeps_pending_rows():
    async with session_factory()() as session:
        pending_before = (
            await session.execute(
                select(func.count()).where(EventOutbox.published.is_(False))
            )
        ).scalar_one()
        await purge_published_outbox(session, retention=timedelta(seconds=0))
        await session.commit()
        pending_after = (
            await session.execute(
                select(func.count()).where(EventOutbox.published.is_(False))
            )
        ).scalar_one()
        assert pending_after == pending_before