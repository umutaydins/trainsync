import { useFormatter, useTranslations } from "next-intl";

const GRAM_DIGITS = 1;

/** kcal and grams in the user's language (`1,890 kcal`, `132,5 g`), and calendar days. */
export function useNutritionFormat() {
  const format = useFormatter();
  const units = useTranslations("common.units");
  const kcal = (value: number) => units("kcal", { value: format.number(value, { maximumFractionDigits: 0 }) });
  const grams = (value: number) => units("g", { value: format.number(value, { maximumFractionDigits: GRAM_DIGITS }) });
  /** A signed balance: `+250 kcal`, `−1,135 kcal`. */
  const signedKcal = (value: number) => `${value > 0 ? "+" : value < 0 ? "−" : ""}${kcal(Math.abs(value))}`;
  /** A calendar day (`YYYY-MM-DD`): `Sun, Oct 18`, or `Sunday, October 18, 2026` in full. */
  const day = (value: string, full = false) =>
    format.dateTime(
      new Date(`${value}T00:00:00Z`),
      full ? { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" } : { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" },
    );
  return { kcal, grams, signedKcal, day };
}
