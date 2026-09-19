"""TEST-labeled institutions must remain distinguishable from real universities."""

from types import SimpleNamespace

from agora_api.research_protocol_service import is_test_institution


def test_test_identity_markers_are_not_real_institutions() -> None:
    assert is_test_institution(
        SimpleNamespace(jurisdiction="TEST", legal_entity_id="123", domain="university.edu")
    )
    assert is_test_institution(
        SimpleNamespace(jurisdiction="MX", legal_entity_id="TEST-123", domain="university.edu")
    )
    assert is_test_institution(
        SimpleNamespace(jurisdiction="MX", legal_entity_id="123", domain="lab.example.org")
    )
    assert not is_test_institution(
        SimpleNamespace(jurisdiction="MX", legal_entity_id="123", domain="university.edu.mx")
    )
