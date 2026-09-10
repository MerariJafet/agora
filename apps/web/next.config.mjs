const agoraApiRewriteTarget =
  process.env.AGORA_API_REWRITE_TARGET ??
  process.env.AGORA_CANONICAL_API_URL ??
  "http://127.0.0.1:8700";
const isDevelopment = process.env.NODE_ENV === "development";
const publicOrigins = [
  process.env.NEXT_PUBLIC_AGORA_API_URL,
  process.env.NEXT_PUBLIC_AGORA_WS_URL,
].flatMap((value) => {
  if (!value || value.startsWith("/")) return [];
  const url = new URL(value);
  if (!["http:", "https:", "ws:", "wss:"].includes(url.protocol)) {
    throw new Error("Public API and realtime URLs must use HTTP(S) or WS(S).");
  }
  const websocket = new URL(url);
  websocket.protocol = url.protocol === "https:" || url.protocol === "wss:" ? "wss:" : "ws:";
  return [url.origin, websocket.origin];
});
const connectSrcApi = [...new Set([
  ...publicOrigins,
  ...(isDevelopment ? [
    "http://127.0.0.1:8700", "http://localhost:8700",
    "ws://127.0.0.1:8700", "ws://localhost:8700",
    "http://127.0.0.1:8710", "http://localhost:8710",
    "ws://127.0.0.1:8710", "ws://localhost:8710",
  ] : []),
])].join(" ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  transpilePackages: ["@agora/sdk-typescript"],
  async rewrites() {
    return [
      {
        source: "/agora-api/:path*",
        destination: `${agoraApiRewriteTarget}/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          {
            key: "Content-Security-Policy",
            value:
              `default-src 'self'; script-src 'self' 'unsafe-inline'${isDevelopment ? " 'unsafe-eval'" : ""}; style-src 'self' 'unsafe-inline'; connect-src 'self' ${connectSrcApi}; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
