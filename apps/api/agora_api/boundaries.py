"""Architecture extension boundaries (interfaces only in Sprint 01).

Each Protocol below is a seam where a future sprint plugs a real
implementation WITHOUT changing callers. Deliberately NOT implemented yet
(per Sprint 01 scope): full A2A conversations, MCP tool suites, live
knowledge providers, arena scoring, world simulation.

Remote-content rule applies to every boundary: data crossing these seams is
untrusted input and can never carry local permission grants.
"""

from typing import Any, Protocol


class A2AAdapter(Protocol):
    """A2A Protocol 1.0.x boundary. AGORA does not invent a competing
    agent-to-agent protocol; it will adapt A2A Agent Cards / tasks here."""

    async def agent_card(self, agent_id: str) -> dict[str, Any]: ...


class MCPAdapter(Protocol):
    """MCP (spec 2026-07-28) boundary — agent-to-tool integration.
    Treated as stateless at the protocol core for the targeted revision."""

    async def list_tools(self) -> list[dict[str, Any]]: ...


class KnowledgeAdapter(Protocol):
    """Knowledge Fabric boundary (OpenAlex, Crossref, PubMed, ... later).
    Future implementations must attach provenance to every result."""

    async def query(self, source: str, query: dict[str, Any]) -> dict[str, Any]: ...


class WorldModule(Protocol):
    """World Module boundary: agent/world-builder created modules run behind
    this seam (sandboxed execution comes in a later sprint)."""

    def module_id(self) -> str: ...


class ArtifactStore(Protocol):
    """Artifact Storage boundary — S3-compatible interface. Stubbed until the
    artifact sprint."""

    async def put(self, key: str, data: bytes, content_type: str) -> str: ...
    async def get(self, key: str) -> bytes: ...


class NullArtifactStore:
    """Explicit stub: raises rather than pretending artifacts persist."""

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        raise NotImplementedError("Artifact storage arrives in a later sprint (ADR-0005).")

    async def get(self, key: str) -> bytes:
        raise NotImplementedError("Artifact storage arrives in a later sprint (ADR-0005).")
