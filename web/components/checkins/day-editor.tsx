"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonClass, inputClass } from "@/components/ui";
import type { Checkin, CheckinIn, CheckinStatus } from "@/lib/checkins";
import { STATUSES, STATUS_META, dayLabel } from "@/lib/checkins";
import { put } from "@/lib/mutate";

function numberOrNull(text: string): number | null {
  const trimmed = text.trim().replace(",", ".");
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

/** Edit one day's check-in; saves with an idempotent `PUT /v1/checkins/{day}` through the BFF. */
export function CheckinDayEditor({
  day,
  checkin,
  save = put,
}: {
  day: string;
  checkin: Checkin | null;
  /** Test seam; defaults to the CSRF-checked BFF write. */
  save?: typeof put;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<CheckinStatus | null>(checkin?.status ?? null);
  const [reason, setReason] = useState(checkin?.reason_note ?? "");
  const [sleep, setSleep] = useState(checkin?.sleep_hours?.toString() ?? "");
  const [energy, setEnergy] = useState(checkin?.energy_1_5?.toString() ?? "");
  const [scale, setScale] = useState(checkin?.body_weight_kg?.toString() ?? "");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === null) {
      setMessage({ ok: false, text: "Choose a status." });
      return;
    }
    const sleepHours = numberOrNull(sleep);
    const scaleKg = numberOrNull(scale);
    if (Number.isNaN(sleepHours) || Number.isNaN(scaleKg)) {
      setMessage({ ok: false, text: "Sleep and scale must be numbers." });
      return;
    }
    const body: CheckinIn = {
      status,
      workout_id: checkin?.workout_id ?? null,
      reason_note: reason.trim() || null,
      sleep_hours: sleepHours,
      energy_1_5: energy ? Number(energy) : null,
      body_weight_kg: scaleKg,
    };
    setSaving(true);
    const result = await save<Checkin>(`/v1/checkins/${day}`, body);
    setSaving(false);
    if (result.ok) {
      setMessage({ ok: true, text: "Saved." });
      router.refresh();
    } else {
      setMessage({ ok: false, text: result.status === 422 ? "Check the values." : result.error });
    }
  }

  return (
    <form onSubmit={submit} aria-labelledby="day-editor-title" className="space-y-4">
      <h2 id="day-editor-title" className="text-sm font-semibold tracking-tight">
        {dayLabel(day)}
      </h2>
      <fieldset>
        <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Status</legend>
        <div className="flex flex-wrap gap-2">
          {STATUSES.map((value) => (
            <label
              key={value}
              className={`flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm ${
                status === value ? "border-accent bg-accent/10" : "border-border"
              }`}
            >
              <input
                type="radio"
                name="status"
                value={value}
                checked={status === value}
                onChange={() => setStatus(value)}
                className="sr-only"
              />
              <span aria-hidden="true">{STATUS_META[value].glyph}</span>
              {STATUS_META[value].label}
            </label>
          ))}
        </div>
      </fieldset>
      <label className="block text-sm">
        <span className="mb-1 block text-muted">Reason or note</span>
        <input className={inputClass} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="grid grid-cols-3 gap-3">
        <label className="block text-sm">
          <span className="mb-1 block text-muted">Sleep (h)</span>
          <input className={inputClass} inputMode="decimal" value={sleep} onChange={(e) => setSleep(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted">Energy (1–5)</span>
          <select className={inputClass} value={energy} onChange={(e) => setEnergy(e.target.value)}>
            <option value="">—</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted">Scale (kg)</span>
          <input className={inputClass} inputMode="decimal" value={scale} onChange={(e) => setScale(e.target.value)} />
        </label>
      </div>
      <div className="flex items-center gap-3">
        <button type="submit" className={buttonClass} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        {message ? (
          <p role={message.ok ? "status" : "alert"} className={`text-sm ${message.ok ? "text-ok" : "text-bad"}`}>
            {message.text}
          </p>
        ) : null}
      </div>
    </form>
  );
}
