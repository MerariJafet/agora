export function resolveRealtimeWsUrl(options: {
  configured?: string;
  api?: string;
  pageUrl?: string;
  legacyPort?: string;
}): string {
  const base = options.pageUrl ?? "http://127.0.0.1:8700";
  const url = new URL(
    options.configured ?? `${(options.api ?? "/agora-api").replace(/\/$/, "")}/v1/realtime/web`,
    base,
  );
  if (!options.configured && !options.api && options.legacyPort && options.pageUrl) {
    url.port = options.legacyPort;
    url.pathname = "/v1/realtime/web";
  }
  if (!["http:", "https:", "ws:", "wss:"].includes(url.protocol)) {
    throw new Error("Realtime URL must use HTTP(S) or WS(S).");
  }
  url.protocol = url.protocol === "https:" || url.protocol === "wss:" ? "wss:" : "ws:";
  return url.toString();
}
