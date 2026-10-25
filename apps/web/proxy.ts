import { NextResponse, type NextRequest } from "next/server";

// Per-request CSP nonce (Next 16 "proxy" convention). Next applies the nonce
// to its own inline scripts during dynamic rendering, so script-src no longer
// needs 'unsafe-inline'. style-src keeps 'unsafe-inline': the UI uses inline
// style attributes, which nonces cannot authorise.
const isDevelopment = process.env.NODE_ENV === "development";
const connectSrc = process.env.AGORA_CSP_CONNECT_SRC ?? "";

export function buildCsp(nonce: string): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDevelopment ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    `connect-src 'self'${connectSrc ? ` ${connectSrc}` : ""}`,
    "img-src 'self' data:",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    // Pages only: API rewrites, build assets and the favicon need no CSP nonce.
    // Prefetch requests are NOT exempted: the global CSP header is gone, so an
    // exemption would let a request carrying those headers get HTML without CSP.
    "/((?!agora-api|_next/static|_next/image|favicon.ico).*)",
  ],
};
