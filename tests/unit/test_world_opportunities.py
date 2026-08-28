import json

from agora_api.boundary import validate_boundary
from agora_api.world import LANDMARKS
from agora_api.world_opportunities import build_opportunity_market


def test_world_opportunity_market_matches_strict_schema():
    market = build_opportunity_market()

    validate_boundary("world-opportunities.schema.json", None, market)

    assert market["classification"] == "public_world_context"
    assert market["directive_boundary"]["remote_content_trust"] == "untrusted_remote"
    assert market["directive_boundary"]["world_offers_options_not_orders"] is True
    assert market["preference_learning"]["classification"] == "inference_not_identity"
    assert {district["district_id"] for district in market["districts"]} == {
        landmark["id"] for landmark in LANDMARKS
    }


def test_world_opportunity_market_cannot_grant_local_permissions():
    market = build_opportunity_market()
    encoded = json.dumps(market, sort_keys=True).lower()

    assert "shell.execute" not in encoded
    assert "files.read" not in encoded
    assert "local_permission_consent" in market["preference_learning"]["forbidden_inferences"]
    assert all(
        district["trust_boundary"]["does_not_authorize_file_shell_git_or_secret_access"]
        for district in market["districts"]
    )
