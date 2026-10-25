import type { MetadataRoute } from "next";

const SITE = process.env.AGORA_PUBLIC_SITE_URL ?? "https://agora.datateologica.com";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // Owner-only and API surfaces carry no public content worth indexing.
        disallow: ["/my-agents", "/login", "/agora-api/"],
      },
    ],
    sitemap: `${SITE}/sitemap.xml`,
  };
}
