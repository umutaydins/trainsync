import type { InviteCreated, Invite, AdminUser } from "@/features/admin/types";
import type { Me, Session, Settings } from "@/features/settings/types";

export function me(overrides: Partial<Me> = {}): Me {
  return {
    id: 2,
    email: "runner@example.com",
    display_name: "Runner",
    role: "user",
    timezone: "Europe/Berlin",
    created_at: "2026-10-01T08:00:00Z",
    ...overrides,
  };
}

export function settings(overrides: Partial<Settings> = {}): Settings {
  return {
    tone: "neutral",
    intensity: "normal",
    profanity: "roast",
    lang: "en",
    checkin_enabled: true,
    stats_digest_enabled: true,
    checkin_time: "21:00:00",
    checkin_reminder_minutes: 90,
    quiet_hours: "23:00-07:00",
    workout_reminder_time: "18:00:00",
    sugar_limit_g: 50,
    country: null,
    emergency_number: "112",
    timezone: "Europe/Berlin",
    custom: [],
    ...overrides,
  };
}

export const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit Version/26.0 Mobile Safari/604.1";
export const MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit Chrome/140.0 Safari/537.36";

export function session(overrides: Partial<Session> = {}): Session {
  return {
    id: 12,
    user_agent: IPHONE,
    created_at: "2026-10-01T08:00:00Z",
    last_seen_at: "2026-10-19T09:30:00Z",
    expires_at: "2026-11-18T09:30:00Z",
    current: true,
    ...overrides,
  };
}

export function invite(overrides: Partial<Invite> = {}): Invite {
  return {
    id: 3,
    note: "for my training partner",
    created_at: "2026-10-19T08:00:00Z",
    expires_at: "2026-10-26T08:00:00Z",
    used_at: null,
    revoked_at: null,
    status: "open",
    ...overrides,
  };
}

export function createdInvite(overrides: Partial<InviteCreated> = {}): InviteCreated {
  return { ...invite({ id: 4, note: "Ayşe" }), code: "Xr2abc", url: "http://localhost:3000/register?invite=Xr2abc", ...overrides };
}

export function adminUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: 2,
    email: "runner@example.com",
    display_name: "Runner",
    role: "user",
    created_at: "2026-10-01T08:00:00Z",
    ...overrides,
  };
}
