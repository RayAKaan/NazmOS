import { MetadataRoute } from "next";

const appUrl = process.env.NEXT_PUBLIC_APP_URL || "https://app.nazm.ai";

const ROUTES = [
  "/",
  "/login",
  "/register",
  "/onboarding",
  "/demo",
  "/product-demo",
  "/privacy",
  "/terms",
  "/dashboard",
  "/inventory",
  "/inventory/expiry",
  "/money-audit",
  "/upload",
  "/feed",
  "/chat",
  "/recovery-match",
  "/suppliers",
  "/team",
  "/settings/autonomy",
  "/integrations",
  "/orchestrator",
  "/chain",
  "/ops",
];

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `${appUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: route === "/" ? "weekly" : "monthly",
    priority: route === "/" ? 1 : 0.6,
  }));
}
