import type { ReactNode } from "react";

import { TrainingNav } from "@/features/training/components/training-nav";

export default function TrainingLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <TrainingNav />
      {children}
    </>
  );
}
