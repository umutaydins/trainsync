/**
 * How far one tap on a stepper moves a set's numbers. Weight moves by the smallest change the
 * plates allow: a pair of 1.25 kg plates on a bar (2.5 kg, the progression's increment, ADR 0018),
 * the usual dumbbell and machine steps alike; kettlebells come in 4 kg steps, added weight on a
 * bodyweight lift or a band in 1 kg.
 */

export const DEFAULT_WEIGHT_STEP_KG = 2.5;
const WEIGHT_STEPS_KG: Record<string, number> = { kettlebell: 4, bodyweight: 1, band: 1 };
export const REPS_STEP = 1;

export function weightStep(equipment: string): number {
  return WEIGHT_STEPS_KG[equipment] ?? DEFAULT_WEIGHT_STEP_KG;
}

/** A typed number (a comma works as the decimal mark); empty or junk counts as 0. */
export function readNumber(text: string): number {
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) ? value : 0;
}

/**
 * `text` moved by `delta`, kept inside `min`..`max` and on `grid` (0.25 kg for weights, 1 for
 * reps), as the text the input shows (`"82.5"`): a typed 80.3 steps to a valid 82.5.
 */
export function stepped(text: string, delta: number, { min, max, grid }: { min: number; max: number; grid: number }): string {
  const next = Math.round((readNumber(text) + delta) / grid) * grid;
  return String(Math.min(max, Math.max(min, next)));
}
