"""Fail closed before a public API starts with development trust material."""

from urllib.parse import urlsplit

from agora_api.config import Settings


def validate_production_settings(settings: Settings) -> None:
    if not settings.is_production:
        return
    failures = []
    for name in ('public_base_url', 'oidc_issuer', 'oidc_redirect_uri'):
        parsed = urlsplit(getattr(settings, name))
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.fragment):
            failures.append(name)
    if not settings.oidc_client_id:
        failures.append('oidc_client_id')
    # This server exchanges codes as a confidential client.
    if not settings.oidc_client_secret:
        failures.append('oidc_client_secret')
    for name in ('world_signing_secret', 'passport_signing_secret'):
        value = getattr(settings, name)
        if len(value) < 32 or value.startswith('agora-dev-'):
            failures.append(name)
    if (not settings.world_signing_key_id
            or settings.world_signing_key_id.startswith('agora-world-dev')):
        failures.append('world_signing_key_id')
    database = urlsplit(settings.database_url.replace('postgresql+asyncpg://', 'postgresql://'))
    if not database.hostname or database.password == 'agora_dev_password':  # noqa: S105
        failures.append('database_url')
    if settings.provenance_class != 'real':
        failures.append('provenance_class')
    for origin in settings.cors_origins:
        parsed = urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.path or parsed.query or parsed.fragment):
            failures.append('cors_origins')
            break
    if failures:
        # Only setting names: validation errors must never contain credential values.
        raise RuntimeError('Unsafe production configuration: ' + ', '.join(failures))
