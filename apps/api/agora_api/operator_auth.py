"""Authentication for the `/v1/operator` plane.

The operator plane is not part of the world: it reads the delivery matrix of
every real Agent (names, device ids, runtime versions) and it mutates world
state — queueing signed rules to the whole population, quarantining records,
sealing experiment ground truth. None of that is an Agent capability, and none
of it belongs to anonymous callers.

It fails closed. When `AGORA_OPERATOR_TOKEN` is unset, there is no operator:
every request is refused, including on a freshly deployed public sandbox.
Forgetting to configure the token locks the door instead of opening it.
"""

from __future__ import annotations

import secrets

from fastapi import Header

from agora_api.config import get_settings
from agora_api.errors import OperatorAuthorityRequired

OPERATOR_TOKEN_HEADER = "X-Agora-Operator-Token"  # noqa: S105 - header name, not a secret
MIN_OPERATOR_TOKEN_LENGTH = 16


async def require_operator(
    presented: str | None = Header(default=None, alias=OPERATOR_TOKEN_HEADER),
) -> None:
    configured = get_settings().operator_token.strip()
    if not configured:
        raise OperatorAuthorityRequired(
            "Operator plane is not configured. Set AGORA_OPERATOR_TOKEN "
            f"(at least {MIN_OPERATOR_TOKEN_LENGTH} characters) to enable it."
        )
    if len(configured) < MIN_OPERATOR_TOKEN_LENGTH:
        raise OperatorAuthorityRequired(
            f"Configured operator token is shorter than {MIN_OPERATOR_TOKEN_LENGTH} "
            "characters; refusing to accept it."
        )
    if presented is None or not secrets.compare_digest(presented, configured):
        raise OperatorAuthorityRequired("Operator token missing or invalid.")
