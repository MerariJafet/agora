import os

from alembic import context
from sqlalchemy import create_engine, pool

from agora_api.models import Base

config = context.config
target_metadata = Base.metadata


def _sync_url() -> str:
    url = os.environ.get(
        "AGORA_DATABASE_URL",
        "postgresql+asyncpg://agora:agora_dev_password@localhost:5434/agora",
    )
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    context.configure(url=_sync_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_sync_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
