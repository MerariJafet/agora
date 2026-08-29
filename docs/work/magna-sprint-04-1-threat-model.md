# MAGNA Sprint 04.1 Threat Model Addendum

Threat: off-chain component is presented as deployed contract.

Control: status and release-manifest views expose only `TokoinFixedSupply` in
`contracts`; all other components are marked as off-chain trust boundaries or
deferred.

Threat: human decision is inferred from recommendation text.

Control: pending ratifications require `decision_value=null`; ratified state is
accepted only from the founder ratification bundle hash
`2bee72496f3c9ddb94a2e3a7cd041df04b205b784acc2110304ab2347dd20088`.

Threat: GET request creates live deployment state.

Control: status, scope matrix, ratification bundle and draft release manifest
are read-only endpoints. Explicit deployment manifest creation remains under
`POST /v1/tokoin-testnet/deployment/local-devnet`.

Threat: premature Sprint 05 continuation.

Control: release report states Sprint 04.1 remains
`PARTIAL_AWAITING_EXTERNAL_AUDIT`; Sprint 05 must not start without accepted
external audit and final go/no-go or a deliberate roadmap change by the human
owner.
