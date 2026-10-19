/**
 * What the API's refusals mean on the auth forms: a message key of the `auth` namespace, on a field
 * where the API names one. Pure, so the mapping is tested without a browser.
 */

/** The API's minimum (core/security.py, PASSWORD_MIN_LENGTH); the forms check it first. */
export const PASSWORD_MIN_LENGTH = 10;

/** Status 0: the request never got an answer (offline, aborted). */
const NO_ANSWER = 0;
const BAD_GATEWAY = 502;
const DEFAULT_RETRY_AFTER_S = 900;
const SECONDS_PER_MINUTE = 60;

export const REGISTER_FIELDS = ["email", "password", "display_name", "invite_code", "timezone"] as const;
export type RegisterField = (typeof REGISTER_FIELDS)[number];

export type RegisterErrorKey =
  | "emailTaken"
  | "invite"
  | "closed"
  | "tooMany"
  | "weakPassword"
  | "invalidField"
  | "invalid"
  | "failed"
  | "network"
  | "backendDown";

export interface RegisterErrors {
  /** Shown above the submit button. */
  form: RegisterErrorKey | null;
  fields: Partial<Record<RegisterField, RegisterErrorKey>>;
}

function isRegisterField(value: unknown): value is RegisterField {
  return typeof value === "string" && (REGISTER_FIELDS as readonly string[]).includes(value);
}

/** Fields named by a 422 `detail` list (`loc: ["body", "<field>", ...]`). */
function invalidFields(detail: unknown): RegisterField[] {
  if (!Array.isArray(detail)) return [];
  return detail.flatMap((item: unknown) => {
    const loc = item && typeof item === "object" ? (item as { loc?: unknown }).loc : undefined;
    const field = Array.isArray(loc) ? loc[1] : undefined;
    return isRegisterField(field) ? [field] : [];
  });
}

/** `POST /api/auth/register` answered `status` with `detail` (the BFF passes the API's on). */
export function registerErrors(status: number, detail?: unknown): RegisterErrors {
  switch (status) {
    case NO_ANSWER:
      return { form: "network", fields: {} };
    case 400:
      return { form: null, fields: { invite_code: "invite" } };
    case 403:
      return { form: "closed", fields: {} };
    case 409:
      return { form: null, fields: { email: "emailTaken" } };
    case 429:
      return { form: "tooMany", fields: {} };
    case BAD_GATEWAY:
      return { form: "backendDown", fields: {} };
    case 422: {
      if (typeof detail === "string" && detail.includes("password")) {
        return { form: null, fields: { password: "weakPassword" } };
      }
      const named = invalidFields(detail);
      return {
        form: "invalid",
        fields: Object.fromEntries(named.map((field) => [field, "invalidField" as const])),
      };
    }
    default:
      return { form: "failed", fields: {} };
  }
}

export type LoginErrorKey = "wrong" | "tooMany" | "failed" | "network";

/** The sign-in form's message; `minutes` for the lockout one. */
export function loginError(status: number, retryAfter: string | null): { key: LoginErrorKey; minutes?: number } {
  if (status === NO_ANSWER) return { key: "network" };
  if (status === 401) return { key: "wrong" };
  if (status === 429) {
    const seconds = Number(retryAfter ?? DEFAULT_RETRY_AFTER_S);
    const valid = Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_RETRY_AFTER_S;
    return { key: "tooMany", minutes: Math.ceil(valid / SECONDS_PER_MINUTE) };
  }
  return { key: "failed" };
}

export type ResetErrorKey = "invalidLink" | "weakPassword" | "failed" | "network";

export function resetError(status: number): ResetErrorKey {
  if (status === NO_ANSWER) return "network";
  if (status === 400) return "invalidLink";
  if (status === 422) return "weakPassword";
  return "failed";
}
