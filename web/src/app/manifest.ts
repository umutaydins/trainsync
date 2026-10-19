import type { MetadataRoute } from "next";
import { getTranslations } from "next-intl/server";

import { THEME_COLORS } from "@/lib/theme";

/**
 * Web app manifest (`/manifest.webmanifest`): installable on Android and iOS home screens, opening
 * on the training page. The service worker (`/sw.js`) caches only the app shell, never API data.
 * Colours are the dark design tokens (--bg): the splash and the status bar match the app.
 */
export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const t = await getTranslations("common");
  return {
    id: "/training",
    name: t("appName"),
    short_name: t("appName"),
    description: t("manifestDescription"),
    start_url: "/training",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: THEME_COLORS.dark,
    theme_color: THEME_COLORS.dark,
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
