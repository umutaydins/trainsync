import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

// The user's language and time zone per request (ADR 0039).
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

// Versions the service worker's shell cache: a new build clears the old shell (ADR 0039).
const buildId = process.env.GIT_SHA || process.env.VERCEL_GIT_COMMIT_SHA || `${Date.now()}`;

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_BUILD_ID: buildId },
  // A self-contained server in .next/standalone for the Docker image.
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default withNextIntl(nextConfig);
