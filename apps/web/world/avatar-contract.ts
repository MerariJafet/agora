import type { AgentSemanticState } from "./types";

export const AGENT_AVATAR_CONTRACT_VERSION = "agora.agent-avatar.v1";

export const AVATAR_LIMITS = {
  portrait: { width: 512, height: 512, maxBytes: 512 * 1024, formats: ["png", "webp"] },
  worldSprite: { width: 256, height: 256, maxBytes: 512 * 1024, formats: ["png", "webp"] },
  animationAtlas: { width: 2048, height: 2048, maxBytes: 2 * 1024 * 1024, maxFrames: 64 },
  cssFootprint: { normalWidth: 48, normalHeight: 64, maxWidth: 56, maxHeight: 72 },
} as const;

export function avatarStatusFor(agent: AgentSemanticState) {
  const schemaVersion = agent.avatar.schema_version;
  const hasSupportedRecipe = Boolean(schemaVersion && agent.avatar.body && agent.avatar.visor);
  return {
    contractVersion: AGENT_AVATAR_CONTRACT_VERSION,
    status: hasSupportedRecipe ? "procedural_recipe_active" : "fallback_active",
    mode: hasSupportedRecipe ? "procedural_recipe" : "fallback",
    note: hasSupportedRecipe
      ? "Avatar procedural dentro del catalogo seguro de AGORA."
      : "Fallback visible hasta que exista una revision valida activa.",
  };
}
