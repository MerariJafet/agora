/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@agora/sdk-typescript"],
  async rewrites() {
    return [
      {
        source: "/agora-api/:path*",
        destination: "http://127.0.0.1:8700/:path*",
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
              "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:8700 http://localhost:8700 ws://127.0.0.1:8700 ws://localhost:8700; img-src 'self' data:",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
