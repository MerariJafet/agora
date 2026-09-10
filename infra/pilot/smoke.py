# ruff: noqa: S603, S607
# Subprocess argv is constructed locally; no shell or remote input is evaluated.
"""Boot only an owned disposable TEST compose project and prove packaging controls."""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    project = "agora-pilot-test-" + secrets.token_hex(6)
    api_image = os.environ.get("AGORA_API_IMAGE", "agora-pilot-api:20260909-local")
    bridge_image = os.environ.get("AGORA_BRIDGE_IMAGE", "agora-pilot-bridge:20260909-local")
    web_image = os.environ.get("AGORA_WEB_IMAGE", "agora-pilot-web:20260909-local")
    env = dict(os.environ)
    env.update(
        {
            "AGORA_PILOT_PROJECT": project,
            "AGORA_API_IMAGE": api_image,
            "AGORA_WEB_IMAGE": web_image,
            "AGORA_PILOT_WEB_PORT": "0",
            "AGORA_PILOT_DB_PASSWORD": secrets.token_hex(24),
            "AGORA_PUBLIC_BASE_URL": "https://test.invalid",
            "AGORA_OIDC_ISSUER": "https://test.invalid",
            "AGORA_OIDC_CLIENT_ID": "TEST_NOT_REAL",
            "AGORA_OIDC_CLIENT_SECRET": secrets.token_hex(24),
            "AGORA_OIDC_REDIRECT_URI": "https://test.invalid/auth/callback",
            "AGORA_WORLD_SIGNING_SECRET": secrets.token_hex(32),
            "AGORA_PASSPORT_SIGNING_SECRET": secrets.token_hex(32),
            "AGORA_WORLD_SIGNING_KEY_ID": "TEST_NOT_REAL",
            "AGORA_WORLD_INSTANCE_ID": project,
            "AGORA_CORS_ORIGINS": '["https://test.invalid"]',
            "AGORA_PILOT_HTTP_PORT": "0",
        }
    )
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(ROOT / "infra/pilot/compose.yml"),
        "-f",
        str(ROOT / "infra/pilot/compose.test.yml"),
    ]
    report = {"classification": "TEST_ONLY_LOCAL_IMAGE_BOOT", "project": project, "status": "FAIL"}
    started = time.monotonic()

    def run(args, expected=0):
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=120)
        if expected is not None and result.returncode != expected:
            raise RuntimeError("packaging smoke command failed: " + args[0])
        return result

    try:
        run(compose + ["config", "--quiet"])
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "90", "postgres", "redis", "nats"])
        run(compose + ["run", "--rm", "migrate"])
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "90", "api"])
        run(compose + ["up", "-d", "--wait", "--wait-timeout", "90", "web"])
        web = run(compose + ["ps", "-q", "web"]).stdout.strip()
        run(
            [
                "docker",
                "exec",
                web,
                "node",
                "-e",
                "Promise.all([fetch('http://127.0.0.1:3000'),fetch('http://127.0.0.1:3000/agora-api/healthz')])"
                ".then(async ([home,api])=>{"
                "if(home.status!==200||api.status!==200)throw Error('http');"
                "const csp=home.headers.get('content-security-policy');"
                "if(!csp||csp.includes('unsafe-eval')||"
                "!csp.includes(\"frame-ancestors 'none'\"))throw Error('csp');"
                "if((await api.json()).status!=='ok')throw Error('proxy');})"
                ".catch(()=>process.exit(1))",
            ]
        )
        if run(["docker", "exec", web, "id", "-u"]).stdout.strip() != "10001":
            raise RuntimeError("Web rootless check failed")
        report.update(
            {
                "web_home_http_ok": True,
                "web_csp_ok": True,
                "web_api_proxy_ok": True,
                "web_uid": 10001,
            }
        )
        api = run(compose + ["ps", "-q", "api"]).stdout.strip()
        # Both login and upgrade traverse the same Next origin; no direct API cookie shortcut.
        browser_probe = """
import asyncio, json
import httpx, websockets
async def check():
    async with httpx.AsyncClient(base_url='http://web:3000', timeout=10) as client:
        login = await client.post('/agora-api/v1/auth/dev/login',
                                  json={'username': 'TEST-pilot-websocket'})
        assert login.status_code == 200
        cookies = '; '.join(f'{name}={value}' for name,value in client.cookies.items())
        assert cookies
        async with websockets.connect('ws://web:3000/agora-api/v1/realtime/web',
                additional_headers={'Cookie': cookies}, open_timeout=10) as ws:
            await ws.send(json.dumps({'type':'subscribe','space_id':'arena'}))
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert frame == {'type':'subscribed','space_id':'arena'}
asyncio.run(check())
"""
        run(["docker", "exec", api, "python", "-c", browser_probe])
        report["web_cookie_login_and_ws_subscribe_ok"] = True
        user = run(["docker", "exec", api, "id", "-u"]).stdout.strip()
        if user != "10001":
            raise RuntimeError("API rootless check failed")
        run(["docker", "exec", api, "python", "/app/infra/pilot/readiness.py"])
        for service in ["postgres", "redis", "nats"]:
            cid = run(compose + ["ps", "-q", service]).stdout.strip()
            ports = json.loads(
                run(
                    ["docker", "inspect", "--format", "{{json .HostConfig.PortBindings}}", cid]
                ).stdout
            )
            if ports:
                raise RuntimeError("infrastructure host port unexpectedly exposed")
        run(
            [
                "docker",
                "exec",
                api,
                "python",
                "-c",
                "from pathlib import Path; p=Path('/data/artifacts/TEST-storage-probe'); "
                "p.write_text('TEST'); assert p.read_text()=='TEST'; p.unlink()",
            ]
        )
        denied = run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "-e",
                "AGORA_ENV=production",
                api_image,
                "python",
                "/app/infra/pilot/assert-production.py",
            ],
            expected=None,
        )
        if denied.returncode == 0:
            raise RuntimeError("empty production configuration accepted")
        bridge = run(["docker", "run", "--rm", "--network", "none", bridge_image, "--help"])
        if "AGORA Bridge" not in bridge.stdout:
            raise RuntimeError("Bridge CLI did not execute")
        run(compose + ["stop", "nats"])
        unhealthy = run(
            ["docker", "exec", api, "python", "/app/infra/pilot/readiness.py"], expected=None
        )
        if unhealthy.returncode == 0:
            raise RuntimeError("readiness ignored broker outage")
        run(compose + ["start", "nats"])
        report.update(
            {
                "status": "PASS",
                "api_uid": int(user),
                "readiness_passed": True,
                "broker_outage_readiness_denied": True,
                "private_infrastructure_ports": True,
                "artifact_volume_writable": True,
                "unconfigured_production_denied": True,
                "bridge_cli_executed": True,
            }
        )
    finally:
        cleaned = run(compose + ["down", "--volumes", "--remove-orphans"], expected=None)
        report["cleanup_ok"] = cleaned.returncode == 0
        report["duration_seconds"] = round(time.monotonic() - started, 2)
        output = ROOT / "audit/buyer-review-2026-09-09/pilot-image-smoke.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
    if not report["cleanup_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
