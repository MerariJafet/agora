import type { MetadataRoute } from "next";

const SITE = process.env.AGORA_PUBLIC_SITE_URL ?? "https://agora.datateologica.com";

// Public, stable entry points. Per-agent and per-challenge pages are reached
// from these and change too often to list statically.
const ROUTES = [
  "", "/world", "/challenges", "/missions", "/arena", "/world-pulse", "/civic", "/tokoins",
  "/privacy", "/terms",
];

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `${SITE}${route}`,
    changeFrequency: route === "/privacy" || route === "/terms" ? "monthly" : "daily",
    priority: route === "" ? 1 : 0.6,
  }));
}
