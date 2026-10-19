import { CircleCheck } from "lucide-react";
import type { ReactNode } from "react";

/** A success line above an auth form ("Password changed"). */
export function SuccessNotice({ children }: { children: ReactNode }) {
  return (
    <p role="status" className="mb-6 flex items-start gap-2 rounded-control bg-ok-soft px-4 py-3 text-sm font-medium text-ok">
      <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
      {children}
    </p>
  );
}
