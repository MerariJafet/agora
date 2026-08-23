"""Canonical boundary validation against packages/protocol JSON Schemas (2020-12).

Security-critical wire payloads are validated with `additionalProperties:
false` semantics — unknown fields are rejected, never silently accepted.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from agora_api.errors import ValidationFailed

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "packages" / "protocol" / "schemas"


@lru_cache
def _registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        resource = Resource.from_contents(schema)
        # Register under both the canonical $id and the bare filename used by relative $refs.
        registry = registry.with_resource(schema["$id"], resource)
        registry = registry.with_resource(path.name, resource)
    return registry


@lru_cache
def _validator(schema_file: str, pointer: str | None = None) -> Draft202012Validator:
    """When `pointer` selects a sub-definition, validate through a `$ref`
    into the still-intact registered resource rather than extracting the
    subtree in isolation. Extracting the subtree would strip its sibling
    `$defs`, breaking any local `#/$defs/...` reference the sub-definition
    itself makes (e.g. `CreateClaimRequest` referencing `#/$defs/ClaimType`
    in the same file)."""
    if pointer:
        schema: dict[str, Any] = {"$ref": f"{schema_file}#{pointer}"}
    else:
        schema = json.loads((SCHEMA_DIR / schema_file).read_text())
    return Draft202012Validator(schema, registry=_registry())


def validate_boundary(schema_file: str, pointer: str | None, payload: Any) -> None:
    validator = _validator(schema_file, pointer)
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.json_path)
    if errors:
        first = errors[0]
        raise ValidationFailed(f"Invalid payload at {first.json_path}: {first.message[:200]}")


def validate_challenge_request(payload: Any) -> None:
    validate_boundary("registration.schema.json", "/$defs/ChallengeRequest", payload)


def validate_register_request(payload: Any) -> None:
    validate_boundary("registration.schema.json", "/$defs/RegisterRequest", payload)


def validate_event_envelope(payload: Any) -> None:
    validate_boundary("event-envelope.schema.json", None, payload)
