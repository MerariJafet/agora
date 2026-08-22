"""AGORA Bridge CLI: agora init | status | connect | pause | resume | revoke."""

import os
import secrets
import sys

import click

from agora_bridge import __version__
from agora_bridge.audit import LocalAuditLog
from agora_bridge.budget import BudgetLimits, BudgetManager
from agora_bridge.client import ApiError, ConnectionClient
from agora_bridge.config import load_config, save_config
from agora_bridge.identity import IdentityManager
from agora_bridge.policy import LocalPermission, LocalPolicyEngine
from agora_bridge.session_store import delete_token, load_token, save_token

audit = LocalAuditLog()


@click.group()
@click.version_option(__version__, prog_name="agora")
def cli() -> None:
    """AGORA Bridge — your agent's edge runtime. Keys and credentials stay local."""


@cli.command()
@click.argument("agent_name")
@click.option("--api-url", default=None, help="AGORA API base URL.")
def init(agent_name: str, api_url: str | None) -> None:
    """Create a local Ed25519 device identity for AGENT_NAME."""
    config = load_config()
    if api_url:
        config.api_url = api_url
    elif os.environ.get("AGORA_BRIDGE_API_URL"):
        config.api_url = os.environ["AGORA_BRIDGE_API_URL"]
    identity = IdentityManager(agent_name)
    if identity.exists():
        click.echo(
            f"Identity for '{agent_name}' already exists "
            f"(backend: {identity.storage_backend})."
        )
        sys.exit(1)
    public_key = identity.generate()
    config.agent_name = agent_name
    save_config(config)
    audit.record("identity.created", agent=agent_name, backend=identity.storage_backend)
    click.echo(f"Created identity for '{agent_name}'.")
    click.echo(f"  key storage : {identity.storage_backend}")
    click.echo(f"  public key  : {public_key}")
    click.echo("  private key : stays on this machine. It is never sent to AGORA.")


@cli.command()
def connect() -> None:
    """Register this agent+device with AGORA via challenge-response."""
    config = load_config()
    if not config.agent_name:
        raise click.ClickException("No agent initialized. Run `agora init <name>` first.")
    if config.paused:
        raise click.ClickException("Bridge is paused. Run `agora resume` first.")
    identity = IdentityManager(config.agent_name)
    client = ConnectionClient(config)
    public_key = identity.public_key()

    challenge = client.request_challenge(public_key, config.agent_name)
    message = client.build_registration_message(challenge, public_key, config.agent_name)
    signature = identity.sign(message)
    try:
        result = client.register(
            challenge=challenge,
            public_key=public_key,
            agent_name=config.agent_name,
            signature=signature,
            idempotency_key=f"bridge-{secrets.token_urlsafe(16)}",
            device_label=os.uname().nodename,
        )
    except ApiError as exc:
        audit.record("connect.failed", agent=config.agent_name, code=exc.code)
        raise click.ClickException(str(exc)) from exc

    config.agent_id = result["agent_id"]
    config.agent_version_id = result["agent_version_id"]
    config.device_id = result["device_id"]
    save_config(config)
    save_token(config.agent_name, result["session_token"])
    audit.record(
        "connect.registered",
        agent=config.agent_name,
        agent_id=config.agent_id,
        device_id=config.device_id,
    )
    click.echo(f"Registered '{config.agent_name}' with AGORA.")
    click.echo(f"  agent_id  : {config.agent_id}")
    click.echo(f"  version   : {config.agent_version_id}")
    click.echo(f"  device_id : {config.device_id}")
    click.echo(f"  session   : valid until {result['session_expires_at']}")


@cli.command()
def status() -> None:
    """Show local identity, connection, policy and budget state."""
    config = load_config()
    click.echo(f"AGORA Bridge v{__version__}")
    click.echo(f"  api_url : {config.api_url}")
    click.echo(f"  agent   : {config.agent_name or '(not initialized)'}")
    click.echo(f"  paused  : {config.paused}")
    if config.agent_name:
        identity = IdentityManager(config.agent_name)
        click.echo(f"  identity: {'present' if identity.exists() else 'MISSING'} "
                   f"(backend: {identity.storage_backend})")
    if config.device_id:
        click.echo(f"  device  : {config.device_id}")
        token = load_token(config.agent_name or "")
        if token:
            try:
                ping = ConnectionClient(config).ping(token)
                click.echo(f"  cloud   : connected ({ping['status']})")
            except ApiError as exc:
                click.echo(f"  cloud   : not connected ({exc.code})")
        else:
            click.echo("  cloud   : no active session")
    engine = LocalPolicyEngine(config)
    click.echo("  local permissions (default deny):")
    for perm in LocalPermission:
        decision = engine.decide(perm)
        verdict = "ALLOW" if decision.allowed else "deny "
        click.echo(f"    {perm.value:18} {verdict} — {decision.reason}")
    budget = BudgetManager(BudgetLimits(**{k: v for k, v in config.budget.items()
                                           if k in BudgetLimits.__dataclass_fields__}))
    click.echo(f"  budget  : {budget.limits.daily_tokens} tokens/day, "
               f"${budget.limits.daily_usd}/day, concurrency {budget.limits.max_concurrency}")


@cli.command()
def pause() -> None:
    """Pause the Bridge: all local permission checks deny while paused."""
    config = load_config()
    config.paused = True
    save_config(config)
    audit.record("bridge.paused", agent=config.agent_name)
    click.echo("Bridge paused. All capability checks now deny.")


@cli.command()
def resume() -> None:
    """Resume the Bridge after a pause."""
    config = load_config()
    config.paused = False
    save_config(config)
    audit.record("bridge.resumed", agent=config.agent_name)
    click.echo("Bridge resumed.")


@cli.command()
@click.confirmation_option(prompt="Revoke this device? Registered sessions stop working.")
def revoke() -> None:
    """Revoke this device with AGORA Cloud (owner kill switch)."""
    config = load_config()
    if not config.device_id:
        raise click.ClickException("No registered device to revoke.")
    result = ConnectionClient(config).revoke(config.device_id)
    if config.agent_name:
        delete_token(config.agent_name)
    audit.record("device.revoked", agent=config.agent_name, device_id=config.device_id)
    click.echo(f"Device {result['device_id']} revoked.")


@cli.command(name="grant")
@click.argument("permission")
def grant(permission: str) -> None:
    """Grant a LOCAL permission (owner-only; never possible from remote data)."""
    try:
        perm = LocalPermission(permission)
    except ValueError:
        valid = ", ".join(p.value for p in LocalPermission)
        raise click.ClickException(f"Unknown permission. Valid: {valid}") from None
    config = load_config()
    if perm.value not in config.granted_permissions:
        config.granted_permissions.append(perm.value)
        save_config(config)
    audit.record("policy.granted", permission=perm.value, source="local-owner-cli")
    click.echo(f"Granted {perm.value} (local grant by owner).")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
