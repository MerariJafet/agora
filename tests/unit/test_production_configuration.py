import pytest
from agora_api.config import Settings
from agora_api.production import validate_production_settings


def valid_settings(**overrides):
    values = dict(
        env='production', public_base_url='https://api.example.org',
        oidc_issuer='https://identity.example.org', oidc_client_id='agora',
        oidc_client_secret='test-client-secret',
        oidc_redirect_uri='https://agora.example.org/login/callback',
        world_signing_secret='x' * 48, passport_signing_secret='y' * 48,
        world_signing_key_id='public-2026-01', provenance_class='real',
        database_url='postgresql+asyncpg://runtime@db.example.org/agora',
        cors_origins=['https://agora.example.org'],
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_development_defaults_rejected_in_production():
    with pytest.raises(RuntimeError, match='Unsafe production configuration'):
        validate_production_settings(Settings(_env_file=None, env='production'))


def test_explicit_production_configuration_accepted():
    validate_production_settings(valid_settings())


@pytest.mark.parametrize(('field', 'value'), [
    ('public_base_url', 'http://api.example.org'),
    ('oidc_issuer', ''),
    ('oidc_redirect_uri', 'https://user:private@example.org/cb'),
    ('oidc_client_id', ''),
    ('oidc_client_secret', ''),
    ('world_signing_secret', 'agora-dev-world-signing-secret-change-me'),
    ('passport_signing_secret', ''),
    ('world_signing_key_id', 'agora-world-dev-2026-08'),
    ('database_url', 'postgresql+asyncpg://agora:agora_dev_password@localhost/agora'),
    ('provenance_class', 'test'),
    ('cors_origins', ['*']),
    ('cors_origins', ['https://site.test/path']),
])
def test_unsafe_setting_fails_without_leaking_value(field, value):
    with pytest.raises(RuntimeError) as failure:
        validate_production_settings(valid_settings(**{field: value}))
    assert field in str(failure.value)
    assert 'private' not in str(failure.value)
    assert 'agora_dev_password' not in str(failure.value)


def test_development_configuration_remains_usable():
    validate_production_settings(Settings(_env_file=None, env='development'))
