import type { ReactNode } from "react";

import { TrainingNav } from "@/components/training/training-nav";

export default function TrainingLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <TrainingNav />
      {children}
    </>
  );
}
