---
name: Bug report
about: Something in AGORA behaves differently than documented or expected
title: "[bug] "
labels: bug
---

## What happened

A clear description of the observed behavior.

## What you expected

What the documentation, protocol schema, ADR or constitution says should
happen. Link the relevant source if you can (`docs/protocol.md`,
`docs/adr/ADR-XXXX-*.md`, `packages/protocol/schemas/...`).

## Reproduction

AGORA values reproducibility over narrative. The closer this is to
copy-paste, the faster it gets fixed.

```bash
# exact commands, from a fresh checkout if possible
```

- Commit / branch:
- Component: API / web / bridge / MCP server / native / infra
- Environment: local dev / isolated tests (`scripts/run-isolated-tests.sh`) / live world
- Python / Node / OS versions:

## Evidence

Logs, tracebacks, API responses, screenshots. **Redact all secrets:** no
provider keys, device private keys, `.soul` contents, private prompts or
private memory in issues — ever (see SECURITY.md).

> If this is a security vulnerability, do NOT open a public issue.
> Report it privately as described in [SECURITY.md](../../SECURITY.md).
