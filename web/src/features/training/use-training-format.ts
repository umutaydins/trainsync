import { useFormatter, useTranslations } from "next-intl";

import type { WorkoutRecord } from "@/features/training/types";

const KG_DIGITS = 2;
const E1RM_DIGITS = 1;

type RecordLike = Pick<WorkoutRecord, "kind" | "value" | "reps">;

/** Kilograms, volumes, records and dates of the training screens in the user's language and zone. */
export function useTrainingFormat() {
  const format = useFormatter();
  const units = useTranslations("common.units");
  const t = useTranslations("training.records");
  const number = (value: number, digits = 0) => format.number(value, { maximumFractionDigits: digits });
  const kg = (value: number, digits = KG_DIGITS) => units("kg", { value: number(value, digits) });
  /** Whole kilograms with separators, for volume totals: `8,240 kg`. */
  const volume = (value: number) => units("kg", { value: number(Math.round(value)) });
  const record = (r: RecordLike) => {
    if (r.kind === "weight_for_reps") return t("weightForReps", { weight: kg(r.value), reps: r.reps ?? "?" });
    if (r.kind === "e1rm") return t("e1rmValue", { weight: kg(r.value, E1RM_DIGITS) });
    return t("volumeValue", { volume: volume(r.value) });
  };
  const kind = (k: WorkoutRecord["kind"]) => t(`kinds.${k}`);
  /** A moment in the user's zone: `Oct 18, 2026, 7:30 PM`. */
  const dateTime = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium", timeStyle: "short" });
  const date = (iso: string) => format.dateTime(new Date(iso), { dateStyle: "medium" });
  /** A calendar day (`YYYY-MM-DD`, no zone). */
  const day = (value: string, withYear = false) =>
    format.dateTime(new Date(`${value}T00:00:00Z`), { day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}), timeZone: "UTC" });
  return { number, kg, volume, record, kind, dateTime, date, day };
}

export type TrainingFormat = ReturnType<typeof useTrainingFormat>;
