import type { ReactNode } from "react";

import { ToastProvider } from "@/components/ui/toast";
import { Sidebar } from "@/features/shell/components/sidebar";
import { TabBar } from "@/features/shell/components/tab-bar";
import { api, load } from "@/lib/api";

/**
 * The signed-in app: sidebar on desktop, bottom tab bar on phones (ADR 0039). The account is read
 * once per request; when the API is down the pages show their own error states.
 */
export default async function AppLayout({ children }: { children: ReactNode }) {
  const me = await load(api.me);
  const isOwner = me.ok && me.data.role === "owner";
  return (
    <ToastProvider>
      <div className="flex min-h-dvh">
        <Sidebar isOwner={isOwner} name={me.ok ? me.data.display_name : ""} />
        <main className="mx-auto w-full min-w-0 max-w-6xl px-4 pb-[calc(var(--spacing-tabbar)+env(safe-area-inset-bottom)+1.5rem)] pt-[max(1.25rem,env(safe-area-inset-top))] sm:px-6 md:pb-10 md:pt-8">
          {children}
        </main>
      </div>
      <TabBar />
    </ToastProvider>
  );
}
