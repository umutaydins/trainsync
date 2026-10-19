import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";
import type { ReactNode } from "react";

import { ServiceWorker } from "@/features/shell/components/service-worker";
import { cn } from "@/lib/cn";
import { DEFAULT_THEME, THEME_COLORS, THEME_COOKIE, isTheme } from "@/lib/theme";

import "@/styles/globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("common");
  return {
    title: { default: t("appName"), template: `%s · ${t("appName")}` },
    robots: { index: false, follow: false },
    manifest: "/manifest.webmanifest",
    icons: { apple: "/icons/apple-touch-icon.png" },
    // Added to the home screen on iOS: full screen, status bar over the page.
    appleWebApp: { capable: true, title: t("appName"), statusBarStyle: "black-translucent" },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_COLORS.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_COLORS.dark },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = await getLocale();
  const messages = await getMessages();
  const chosen = (await cookies()).get(THEME_COOKIE)?.value;
  const theme = isTheme(chosen) ? chosen : DEFAULT_THEME;
  return (
    <html lang={locale} className={cn(theme, GeistSans.variable, GeistMono.variable)}>
      <body className="font-sans text-text antialiased">
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
        <ServiceWorker />
      </body>
    </html>
  );
}
