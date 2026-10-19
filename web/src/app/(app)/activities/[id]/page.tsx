import { ArrowLeft } from "lucide-react";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActivityDetailCard } from "@/features/activities/components/activity-detail";
import { LastSynced } from "@/features/shell/components/last-synced";
import { LoadFailed } from "@/features/shell/components/load-failed";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

const NOT_FOUND = 404;
type Props = { params: Promise<{ id: string }> };

function parseId(raw: string): number | null {
  return /^\d{1,20}$/.test(raw) ? Number(raw) : null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const id = parseId((await params).id);
  const result = id === null ? null : await load(() => api.activity(id));
  if (result?.ok) return { title: result.data.activity.name };
  const t = await getTranslations("activities");
  return { title: t("activity") };
}

export default async function ActivityPage({ params }: Props) {
  const id = parseId((await params).id);
  if (id === null) notFound();
  const t = await getTranslations("activities");
  const result = await load(() => api.activity(id));
  if (!result.ok && result.status === NOT_FOUND) notFound();
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/activities" className="-ml-2 inline-flex h-touch items-center gap-1.5 rounded-control px-2 text-sm font-semibold text-muted hover:text-text">
          <ArrowLeft aria-hidden className="size-4" />
          {t("back")}
        </Link>
        {result.ok ? <LastSynced at={result.data.last_synced_at} /> : null}
      </div>
      {result.ok ? <ActivityDetailCard activity={result.data.activity} /> : <LoadFailed title={t("detailFailed")} status={result.status} />}
    </div>
  );
}
