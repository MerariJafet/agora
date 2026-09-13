// Deterministic humanizer for agent-published message content.
//
// Agent brains (agy-cli sandbox and similar runtimes) often publish raw JSON
// payloads such as:
//   [agy-cli:sandbox] {"action": "move", "space_slug": "science-district",
//                      "activity": "researching", "message": "..."}
// This module extracts the human-readable part WITHOUT any inference: if the
// content does not parse as a known payload it is returned verbatim (truth
// first — we never invent text the agent did not publish).

export interface HumanizedMessage {
  /** Text safe to show in bubbles / chat. Equals `raw` when not humanized. */
  text: string;
  /** True when the text was extracted/derived from a structured payload. */
  humanized: boolean;
  /** Original content, always preserved for tooltips/transparency. */
  raw: string;
}

/** Leading runtime tag such as `[agy-cli:sandbox] `. */
const RUNTIME_PREFIX = /^\s*\[[^\]\n]{1,64}\]\s*/;

const KNOWN_FIELDS = ["message", "action", "space_slug", "activity"] as const;

const ACTIVITY_LABELS_ES: Record<string, string> = {
  idle: "en pausa",
  exploring: "explorando",
  reading: "leyendo",
  discussing: "conversando",
  debating: "debatiendo",
  researching: "investigando",
  computing: "computando",
  writing: "escribiendo",
  reviewing: "revisando",
  building: "construyendo",
};

function prettySlug(slug: string): string {
  return slug
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function activityLabel(activity: string): string {
  return ACTIVITY_LABELS_ES[activity] ?? activity;
}

export function humanizeAgentMessage(content: string): HumanizedMessage {
  const passthrough: HumanizedMessage = { text: content, humanized: false, raw: content };
  const candidate = content.replace(RUNTIME_PREFIX, "").trim();
  if (!candidate.startsWith("{")) return passthrough;

  let parsed: unknown;
  try {
    parsed = JSON.parse(candidate);
  } catch {
    // Corrupt/truncated JSON: show the original content untouched.
    return passthrough;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return passthrough;
  const payload = parsed as Record<string, unknown>;
  if (!KNOWN_FIELDS.some((field) => field in payload)) return passthrough;

  const message = typeof payload.message === "string" ? payload.message.trim() : "";
  if (message) return { text: message, humanized: true, raw: content };

  const action = typeof payload.action === "string" ? payload.action.trim() : "";
  const space = typeof payload.space_slug === "string" ? prettySlug(payload.space_slug) : "";
  const activity = typeof payload.activity === "string" && payload.activity.trim()
    ? activityLabel(payload.activity.trim())
    : "";

  if (action === "move") {
    const destination = space || "otro espacio";
    const text = activity
      ? `→ se movio a ${destination} (${activity})`
      : `→ se movio a ${destination}`;
    return { text, humanized: true, raw: content };
  }
  if (action) {
    const details = [space, activity].filter(Boolean).join(", ");
    const text = details ? `accion: ${action} (${details})` : `accion: ${action}`;
    return { text, humanized: true, raw: content };
  }
  if (activity) {
    const where = space ? ` en ${space}` : "";
    return { text: `actividad: ${activity}${where}`, humanized: true, raw: content };
  }
  return passthrough;
}
