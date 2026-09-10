# Web and TypeScript review — 2026-09-09

Scope: `apps/web` and `packages/sdk-typescript`. Internal Codex engineering review; not an independent external security audit. No deployment, live login, shared database mutation, or cryptocurrency action performed. Pre-existing dirty `apps/web/next-env.d.ts` preserved byte-for-byte around every build.

## Findings repaired

1. **Critical dependency advisories:** initial `npm audit --json` found 3 vulnerable packages: Next.js (critical, GHSA-p293-qw3h-jr36 and GHSA-2xp9-vwfh-vxw4), sharp (high, GHSA-rgj7-g3m4-5g8c), js-yaml (high, GHSA-2883-xcg3-v3hh). `npm audit fix` updated the existing allowed dependency graph to Next **16.3.4**, sharp **0.35.4**, js-yaml **4.3.2**. Final npm audit: **0 vulnerabilities**. Windows-specific exploit applicability differs from this Linux host; the vulnerable package is patched regardless.
2. **Missing production owner login UI:** login previously offered only `/v1/auth/dev/login`. Added OIDC start and `/login/callback`, cookie-bearing requests, per-tab state binding, rejection before exchange on missing/mismatched state, removal of one-time credentials from browser history, and a single exchange guarded against duplicate React effects. Development username form is visible only under `NODE_ENV=development`. Production issuer redirect must be HTTPS. Backend browser-bound cookie validation is handled separately by root's backend changes.
3. **Public realtime URL:** browser default previously dialed the page hostname on port 8700, bypassing the frontend proxy and breaking common HTTPS hosting. It now defaults to the same-origin `/agora-api/v1/realtime/web` upgrade route; explicit API/WS settings and the legacy explicit port remain supported. Next's installed router-server supports external rewrite websocket upgrades. Actual TLS ingress upgrade is still a deployment acceptance check.
4. **CSP:** production no longer permits `unsafe-eval` or hard-coded loopback endpoints. API/WS public origins are derived from explicit configuration. Added `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`. Existing static inline hydration/style allowances remain. Pixi's `pixi.js/unsafe-eval` compatibility module is imported: despite its name, this installs precompiled fallbacks that work *without* eval.
5. **World bootstrap loop:** isolated browser reproduction with a manifest lacking ETag never reached canvas initialization. The boot effect depended on `spaces`, derived from a freshly fetched manifest, causing teardown/reinitialization on every fetch. The realtime handler now resolves names from the current store, removing that unstable dependency. Reproduction now reaches a visible canvas.
6. **SDK scope honesty:** corrected TypeScript package description and entrypoint comment. It is a private internal package of manually written read-view types, not a published registration/signing/transport SDK. No generated wire-type files are checked in. Python bridge remains the integration route; a public TypeScript client requires separate implementation and compatibility tests.

## Verification executed

Working directory `$AGORA_REPO/apps/web` unless stated otherwise.

- `npm run lint`: exit 0, no warnings after final changes.
- `npm run typecheck`: exit 0.
- `npm run test:unit`: **38 passed / 0 failed** (33 existing world tests + 5 realtime URL tests). Node reports an existing module-type inference performance warning during unfiltered output.
- `npm run build`: exit 0, Next 16.3.4; 17 static pages generated plus dynamic routes; `/login/callback` included. Build wrapper printed `Preserved pre-existing next-env.d.ts: True`.
- `npm audit --json`: exit 0, vulnerabilities total **0** for the web dependency graph. The private SDK has no standalone installed dependency tree; its optional generation tooling was not separately installed/audited, and is not part of the production web runtime.
- `npm ls next sharp js-yaml`: Next 16.3.4, sharp 0.35.4, js-yaml 4.3.2.
- `git diff --check -- apps/web packages/sdk-typescript`: exit 0.
- `node node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port 3099`: isolated production frontend; stopped after smoke.
- From home/workspace: `node $AGORA_REPO/audit/launch-2026-09-09/web-smoke.cjs`: real headless Chromium via locally installed Playwright. **All API calls and websocket connections intercepted with TEST_NOT_REAL fixtures**, with no live backend access.

Observed final browser output:

```text
PASS production login hides dev form; OIDC start redirects to HTTPS issuer
PASS browser-bound state callback exchanged once; navigation to my-agents; state removed
PASS invalid callback rejected before API request; URL credentials removed
PASS no browser runtime errors; production CSP excludes eval
PASS Pixi world renders visible canvas under production CSP with isolated fixture and mocked websocket
```

Artifacts: `web-smoke.cjs` (reproduction), `web-login-callback.png`, `web-world-mock.png`. These images are synthetic UI verification, not adoption, live science, or institutional endorsement evidence.

## Remaining launch acceptance checks

- Configure a real OIDC issuer/client/secret and redirect URI `https://PUBLIC_HOST/login/callback`; complete a real staging owner login, claim, revoke, logout and expired-session flow. Browser mocks establish UI behavior only.
- Validate HTTPS reverse proxy, same-site cookies and websocket upgrade in the chosen deployment. Prefer same-origin frontend/API routing. `NEXT_PUBLIC_*` and rewrites are build configuration: rebuild after changing public deployment URLs. If using the legacy separate port in production, configure its explicit public WS URL for CSP too.
- Current CSP retains inline scripts/styles for static Next hydration. A stricter nonce or hash-based policy is a future hardening task requiring dynamic-rendering/performance decisions and a full browser regression pass.
- No comprehensive accessibility, mobile-browser, load, or external penetration test was performed here. Headless Chromium software WebGL success is not hardware compatibility certification.
- Public npm TypeScript SDK is not ready; package intentionally remains private. Do not advertise it as an agent client.
- Build warns that `$HOME/package.json` is outside the Git repository; successful build uses the AGORA repository boundary. This warning does not prevent production compilation.
- `/tokoins` currently labels the internal chain and external candidate separately and explicitly states bundle integrity is not deployment, decentralization or value. Preserve these boundaries in publication material.
