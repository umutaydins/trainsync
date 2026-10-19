import { useFormatter, useTranslations } from "next-intl";

import { durationParts } from "@/lib/format";

/** A duration in the user's language: `25h 24m`, `25 sa 24 dk`; `45m` under an hour, `2h` on the hour. */
export function useDuration(): (seconds: number) => string {
  const units = useTranslations("common.units");
  const format = useFormatter();
  return (seconds) => {
    const { hours, minutes } = durationParts(seconds);
    const values = { hours: format.number(hours), minutes: format.number(minutes) };
    if (hours === 0) return units("durationM", values);
    return minutes === 0 ? units("durationH", values) : units("durationHm", values);
  };
}
