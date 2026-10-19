import type { ReactNode } from "react";

import { AppHeader } from "@/features/shell/components/app-header";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <AppHeader />
      <main className="mx-auto w-full max-w-6xl px-4 pb-16 pt-6 sm:px-6">{children}</main>
    </>
  );
}
