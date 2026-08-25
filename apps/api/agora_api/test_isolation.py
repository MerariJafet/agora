"""Fail-closed guard for mutating test runs."""

from __future__ import annotations

from urllib.parse import urlparse

from agora_api.config import get_settings

KNOWN_DEV_DATABASES = {"agora", "agora_dev", "postgres"}
KNOWN_DEV_REDIS = {"redis://localhost:6380/0", "redis://127.0.0.1:6380/0"}


class UnsafeTestEnvironment(RuntimeError):
    pass


def _database_name(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://"))
    return parsed.path.lstrip("/")


def assert_safe_test_environment() -> None:
    settings = get_settings()
    if settings.env != "test":
        raise UnsafeTestEnvironment("AGORA_ENV must be test for mutating test runs.")
    if settings.allow_dev_db_tests:
        return
    db_name = _database_name(settings.database_url)
    if db_name in KNOWN_DEV_DATABASES or not db_name.startswith("agora_test_"):
        raise UnsafeTestEnvironment(
            f"Refusing to run mutating tests against database {db_name!r}."
        )
    if settings.redis_url in KNOWN_DEV_REDIS:
        raise UnsafeTestEnvironment("Refusing to run mutating tests against development Redis.")
    if settings.run_id in {"manual", "dev", "development", ""}:
        raise UnsafeTestEnvironment("AGORA_RUN_ID must be unique for isolated tests.")
