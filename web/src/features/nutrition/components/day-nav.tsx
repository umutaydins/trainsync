import { ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { addDays } from "@/features/nutrition/types";

/** Previous day, back to today, next day (never past today), as links: the day lives in the URL. */
export function DayNav({ date, today }: { date: string; today: string }) {
  const t = useTranslations("nutrition.nav");
  return (
    <nav aria-label={t("label")} className="flex items-center gap-1">
      <Button asChild variant="secondary" size="icon">
        <Link href={`/nutrition?date=${addDays(date, -1)}`} aria-label={t("previous")}>
          <ChevronLeft aria-hidden />
        </Link>
      </Button>
      {date !== today ? (
        <Button asChild variant="secondary">
          <Link href="/nutrition">{t("today")}</Link>
        </Button>
      ) : null}
      {date < today ? (
        <Button asChild variant="secondary" size="icon">
          <Link href={`/nutrition?date=${addDays(date, 1)}`} aria-label={t("next")}>
            <ChevronRight aria-hidden />
          </Link>
        </Button>
      ) : null}
    </nav>
  );
}
