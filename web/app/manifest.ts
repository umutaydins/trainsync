import type { MetadataRoute } from "next";

/**
 * Web app manifest (`/manifest.webmanifest`): installable on Android and iOS home screens, opening
 * on the training page. No service worker: nothing (least of all API data) is cached offline.
 * Colours are the light design tokens (--bg, --accent).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/training",
    name: "trainsync",
    short_name: "trainsync",
    description: "Private training dashboard: workouts, programs, nutrition and Strava data",
    start_url: "/training",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f6f7f9",
    theme_color: "#2f6fde",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
