# MAGNA Sprint 04.1 Threat Model Addendum

Threat: off-chain component is presented as deployed contract.

Control: status and release-manifest views expose only `TokoinFixedSupply` in
`contracts`; all other components are marked as off-chain trust boundaries or
deferred.

Threat: pending human decision is inferred from recommendation text.

Control: ratification schema requires pending decisions to keep
`decision_value=null`, no signer, no timestamp and no evidence hash.

Threat: GET request creates live deployment state.

Control: status, scope matrix, ratification bundle and draft release manifest
are read-only endpoints. Explicit deployment manifest creation remains under
`POST /v1/tokoin-testnet/deployment/local-devnet`.

Threat: premature Sprint 05 continuation.

Control: release report states Sprint 04 remains
`PARTIAL_AWAITING_RATIFICATION`; Sprint 05 must not start without external
audit and ratification or a deliberate roadmap change by the human owner.
