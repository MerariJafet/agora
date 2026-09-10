"""Container readiness: API PostgreSQL/Redis checks plus the configured NATS server."""

import asyncio
import json
import urllib.request

import nats
from agora_api.config import get_settings


async def main():
    with urllib.request.urlopen("http://127.0.0.1:8700/healthz", timeout=3) as response:
        body = json.load(response)
        if response.status != 200 or body.get("status") != "ok":
            raise RuntimeError("API dependency readiness failed")
    connection = await nats.connect(
        get_settings().nats_url, connect_timeout=3, max_reconnect_attempts=0
    )
    try:
        await connection.flush(timeout=2)
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(asyncio.wait_for(main(), timeout=6))
    except Exception:
        # Never return connection strings or credentials in Docker health output.
        raise SystemExit("readiness failed") from None
