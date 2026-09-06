import pytest
from agora_api.agent_identity import IDENTITY_DOMAIN
from agora_api.world_signing import verify_canonical_payload

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


async def test_identity_credential_is_unique_deterministic_and_verifiable(
    api_client, unique_name
):
    first = await register_agent(api_client, SigningKeypair(), f"{unique_name}-identity-a")
    second = await register_agent(api_client, SigningKeypair(), f"{unique_name}-identity-b")

    first_response = await api_client.get(
        f"/v1/agents/{first['agent_id']}/identity-credential"
    )
    repeated_response = await api_client.get(
        f"/v1/agents/{first['agent_id']}/identity-credential"
    )
    second_response = await api_client.get(
        f"/v1/agents/{second['agent_id']}/identity-credential"
    )

    assert first_response.status_code == 200, first_response.text
    first_body = first_response.json()
    repeated_body = repeated_response.json()
    second_body = second_response.json()
    assert first_body == repeated_body
    assert first_body["credential"]["credential_id"] != second_body["credential"]["credential_id"]
    assert first_body["credential"]["non_transferable_token_mirror"]["token_id"] != (
        second_body["credential"]["non_transferable_token_mirror"]["token_id"]
    )

    trusted = {
        key["key_id"]: key["public_key"]
        for key in first_body["trust_bootstrap"]["active_keys"]
    }
    assert verify_canonical_payload(
        first_body["credential"],
        first_body["signature"],
        domain=IDENTITY_DOMAIN,
        trusted_public_keys=trusted,
    )


async def test_identity_credential_is_not_authority_or_private_key_material(
    api_client, unique_name
):
    registration = await register_agent(
        api_client, SigningKeypair(), f"{unique_name}-identity-boundary"
    )
    response = await api_client.get(
        f"/v1/agents/{registration['agent_id']}/identity-credential"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    mirror = body["credential"]["non_transferable_token_mirror"]
    assert mirror["state"] == "not_minted"
    assert mirror["network"] is None
    assert mirror["contract_address"] is None
    assert mirror["required_for_world_entry"] is False
    assert mirror["grants_authority"] is False
    assert mirror["grants_local_permissions"] is False
    assert body["credential"]["trust"]["private_key_material_included"] is False
    assert "private_key" not in body["credential"]["subject"]
    assert "seed_phrase" not in body["credential"]["subject"]


async def test_identity_credential_tampering_is_rejected(api_client, unique_name):
    registration = await register_agent(
        api_client, SigningKeypair(), f"{unique_name}-identity-tamper"
    )
    body = (
        await api_client.get(f"/v1/agents/{registration['agent_id']}/identity-credential")
    ).json()
    body["credential"]["subject"]["name"] = "Impostor"
    trusted = {
        key["key_id"]: key["public_key"] for key in body["trust_bootstrap"]["active_keys"]
    }
    from agora_api.errors import SignatureInvalid

    with pytest.raises(SignatureInvalid):
        verify_canonical_payload(
            body["credential"],
            body["signature"],
            domain=IDENTITY_DOMAIN,
            trusted_public_keys=trusted,
        )
