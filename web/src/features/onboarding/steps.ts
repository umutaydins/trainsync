import type { StravaReturn } from "@/features/onboarding/types";

/** The onboarding steps in order; every one but the last can be skipped. */
export const STEPS = ["timezone", "language", "coach", "strava", "telegram", "profile", "done"] as const;
export type Step = (typeof STEPS)[number];

/** Back from Strava's OAuth page the flow continues at the Strava step, else at the start. */
export function initialStep(stravaReturn: StravaReturn): number {
  return stravaReturn ? STEPS.indexOf("strava") : 0;
}

export function nextStep(index: number): number {
  return Math.min(index + 1, STEPS.length - 1);
}

export function previousStep(index: number): number {
  return Math.max(index - 1, 0);
}

export function isLast(index: number): boolean {
  return index === STEPS.length - 1;
}

/** `?connected=1` / `?connect_error=<reason>` of the OAuth return, or null. */
export function stravaReturnFrom(params: Record<string, string | string[] | undefined>): StravaReturn {
  const error = params.connect_error;
  if (typeof error === "string" && error) return { error };
  return params.connected === "1" ? { connected: true } : null;
}
