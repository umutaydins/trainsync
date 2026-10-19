import "server-only";

import type { RegistrationMode } from "@/features/auth/types";
import { authRequest } from "@/lib/upstream";

const MODES: readonly RegistrationMode[] = ["invite", "open", "closed"];

/** How accounts are created (`GET /v1/auth/registration`, no session), or null if unknown. */
export async function registrationMode(): Promise<RegistrationMode | null> {
  const result = await authRequest("GET", "/v1/auth/registration", null);
  if (!result.ok) return null;
  const mode = (result.data as { mode?: unknown } | null)?.mode;
  return MODES.find((known) => known === mode) ?? null;
}
