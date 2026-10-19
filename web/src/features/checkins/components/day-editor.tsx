"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import type { Checkin, CheckinIn, CheckinStatus } from "@/features/checkins/checkins";
import { STATUSES, STATUS_META, dayLabel } from "@/features/checkins/checkins";
import { put } from "@/lib/mutate";

const ENERGY_LEVELS = [1, 2, 3, 4, 5] as const;
const UNPROCESSABLE = 422;

type Message = { ok: true } | { ok: false; key: "chooseStatus" | "numbers" | "invalid" | "failed" };

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
  const t = useTranslations("checkins");
  const common = useTranslations("common.actions");
  const locale = useLocale();
  const router = useRouter();
  const [status, setStatus] = useState<CheckinStatus | null>(checkin?.status ?? null);
  const [reason, setReason] = useState(checkin?.reason_note ?? "");
  const [sleep, setSleep] = useState(checkin?.sleep_hours?.toString() ?? "");
  const [energy, setEnergy] = useState(checkin?.energy_1_5?.toString() ?? "");
  const [scale, setScale] = useState(checkin?.body_weight_kg?.toString() ?? "");
  const [message, setMessage] = useState<Message | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === null) return setMessage({ ok: false, key: "chooseStatus" });
    const sleepHours = numberOrNull(sleep);
    const scaleKg = numberOrNull(scale);
    if (Number.isNaN(sleepHours) || Number.isNaN(scaleKg)) return setMessage({ ok: false, key: "numbers" });
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
      setMessage({ ok: true });
      router.refresh();
    } else {
      setMessage({ ok: false, key: result.status === UNPROCESSABLE ? "invalid" : "failed" });
    }
  }

  return (
    <form onSubmit={submit} aria-labelledby="day-editor-title" className="flex flex-col gap-4">
      <h2 id="day-editor-title" className="text-xl font-bold tracking-tight">
        {dayLabel(locale, day)}
      </h2>
      <fieldset>
        <legend className="mb-2 text-label font-semibold uppercase tracking-[0.08em] text-muted">{t("editor.status")}</legend>
        <div className="flex flex-wrap gap-2">
          {STATUSES.map((value) => (
            <label
              key={value}
              className={cn(
                "flex h-touch cursor-pointer items-center gap-2 rounded-full border px-4 text-sm font-medium has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent/40",
                status === value ? "border-accent bg-accent-soft text-accent-ink" : "border-border",
              )}
            >
              <input type="radio" name="status" value={value} checked={status === value} onChange={() => setStatus(value)} className="sr-only" />
              <span aria-hidden="true">{STATUS_META[value].glyph}</span>
              {t(`statuses.${value}`)}
            </label>
          ))}
        </div>
      </fieldset>
      <Field label={t("editor.note")}>
        <Input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
      </Field>
      <div className="grid grid-cols-3 gap-3">
        <Field label={t("editor.sleep")}>
          <Input inputMode="decimal" value={sleep} onChange={(e) => setSleep(e.target.value)} />
        </Field>
        <Field label={t("editor.energy")}>
          <Select value={energy} onChange={(e) => setEnergy(e.target.value)}>
            <option value="">—</option>
            {ENERGY_LEVELS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
        </Field>
        <Field label={t("editor.scale")}>
          <Input inputMode="decimal" value={scale} onChange={(e) => setScale(e.target.value)} />
        </Field>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={saving}>
          {saving ? common("saving") : common("save")}
        </Button>
        {message ? (
          <p role={message.ok ? "status" : "alert"} className={cn("text-sm font-medium", message.ok ? "text-ok" : "text-bad")}>
            {message.ok ? t("editor.saved") : t(`editor.${message.key}`)}
          </p>
        ) : null}
      </div>
    </form>
  );
}
