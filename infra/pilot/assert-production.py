"""Preflight production configuration without connecting or printing secrets."""

from agora_api.config import get_settings
from agora_api.production import validate_production_settings

settings = get_settings()
if not settings.is_production:
    raise SystemExit("production environment required")
validate_production_settings(settings)
print("production configuration accepted; external identity/connectivity not yet verified")
