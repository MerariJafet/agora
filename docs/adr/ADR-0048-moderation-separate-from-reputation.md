# ADR-0048: Moderation Actions Separate From Reputation

Status: Accepted

Moderation reports and admin actions are operational safety controls. They are
audited in their own tables/events and carry `reputation_effect=none`.

Scientific reputation remains multidimensional and evidence-linked. A
quarantine, suspend, revoke, appeal, review or resolve action does not create
Arena Points, truth scores or reputation deltas.
