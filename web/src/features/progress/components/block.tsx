import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { Failure } from "@/components/ui/states";
import type { Period } from "@/features/progress/types";

/**
 * One block of the progress screen: a card with a bold heading. `data-period` tells which period
 * it shows (the e2e test checks that a switch updates every block).
 */
export function Block({
  id,
  title,
  period,
  action,
  className,
  children,
}: {
  id: string;
  title: ReactNode;
  period: Period;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Card id={id} aria-labelledby={`${id}-title`} data-block={id} data-period={period} className={className}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 id={`${id}-title`} className="text-lg font-bold tracking-tight">
          {title}
        </h2>
        {action}
      </div>
      <div className="flex flex-col gap-4">{children}</div>
    </Card>
  );
}

/** A block whose data did not load: the rest of the page stays. */
export function BlockFailure({ error }: { error: string }) {
  const t = useTranslations("progress");
  return <Failure title={t("failed")} message={error} />;
}

/** A quiet "nothing in this period" line inside a block. */
export function BlockEmpty({ children }: { children: ReactNode }) {
  return <p className="rounded-control border border-dashed border-border px-4 py-6 text-center text-sm text-muted">{children}</p>;
}

/** The grid of stat cards of a block (a `<dl>`, each StatCard is one term and its value). */
export function StatGrid({ children, className }: { children: ReactNode; className?: string }) {
  return <dl className={className ?? "grid grid-cols-2 gap-2 sm:grid-cols-4"}>{children}</dl>;
}
