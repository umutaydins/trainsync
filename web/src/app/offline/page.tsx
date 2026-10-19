import { WifiOff } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { Logo } from "@/features/shell/components/logo";

/** Shown by the service worker when a page cannot be loaded (no data on it). */
export default async function Offline() {
  const t = await getTranslations("common.states");
  return (
    <main className="grid min-h-dvh place-items-center px-6 text-center">
      <div className="flex max-w-sm flex-col items-center gap-4">
        <Logo className="size-12" />
        <WifiOff aria-hidden className="size-8 text-muted" />
        <h1 className="text-2xl font-bold tracking-tight">{t("offlineTitle")}</h1>
        <p className="text-muted">{t("offlineBody")}</p>
      </div>
    </main>
  );
}
