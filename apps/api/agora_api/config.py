from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGORA_", env_file=".env", extra="ignore")

    env: Literal["development", "production"] = "development"
    database_url: str = "postgresql+asyncpg://agora:agora_dev_password@localhost:5434/agora"
    redis_url: str = "redis://localhost:6380/0"
    nats_url: str = "nats://localhost:4222"
    api_host: str = "127.0.0.1"
    api_port: int = 8700
    log_level: str = "INFO"

    # Generic OIDC (production AuthProvider). Empty = not configured;
    # production then fails closed on login (SEC-011 / ADR-0019).
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""

    # Canonical public origin used to build signable Agent Cards (S3-G01).
    public_base_url: str = "http://127.0.0.1:8700"

    # Sprint 05: ArtifactStore (local filesystem, content-addressed).
    artifact_store_root: str = "~/.agora/artifact-store"
    artifact_max_bytes: int = 200 * 1024 * 1024

    challenge_ttl_seconds: int = 300
    session_ttl_seconds: int = 3600
    # Registration-sensitive rate limits (per client IP, fixed window).
    ratelimit_window_seconds: int = 60
    ratelimit_max_requests: int = 30
    # Outbox publisher
    outbox_poll_interval_seconds: float = 0.5
    outbox_enabled: bool = True

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
