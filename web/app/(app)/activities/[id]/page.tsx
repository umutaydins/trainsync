import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ActivityDetailCard } from "@/components/activities/activity-detail";
import { LastSynced } from "@/components/last-synced";
import { ErrorState } from "@/components/ui";
import { api, load } from "@/lib/api";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

function parseId(raw: string): number | null {
  return /^\d{1,20}$/.test(raw) ? Number(raw) : null;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const id = parseId((await params).id);
  const result = id === null ? null : await load(() => api.activity(id));
  return { title: result?.ok ? result.data.activity.name : "Activity" };
}

export default async function ActivityPage({ params }: Props) {
  const id = parseId((await params).id);
  if (id === null) notFound();
  const result = await load(() => api.activity(id));
  if (!result.ok && result.status === 404) notFound();
  return (
    <>
      <div className="mb-4 flex items-center justify-between gap-3">
        <Link href="/activities" className="text-sm text-muted hover:text-text">← Activities</Link>
        {result.ok ? <LastSynced at={result.data.last_synced_at} /> : null}
      </div>
      {result.ok ? (
        <ActivityDetailCard activity={result.data.activity} />
      ) : (
        <ErrorState title="Could not load this activity" message={result.error} />
      )}
    </>
  );
}
