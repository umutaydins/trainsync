import { NextResponse, type NextRequest } from "next/server";

import { serverEnv } from "@/lib/env";
import {
  SESSION_COOKIE,
  SESSION_MAX_AGE_S,
  createSessionToken,
  passwordMatches,
  safeNextPath,
} from "@/lib/session";

export const dynamic = "force-dynamic";

/** Form or JSON body `{password, next?}`. 303 to `next` with a session cookie, or 401. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const { password, next } = await readCredentials(request);
  const env = serverEnv();
  if (!passwordMatches(password, env.dashboardPassword)) {
    return NextResponse.json({ error: "wrong password" }, { status: 401 });
  }
  const response = NextResponse.redirect(new URL(safeNextPath(next), request.url), 303);
  response.cookies.set(SESSION_COOKIE, createSessionToken(env.sessionSecret, new Date()), {
    httpOnly: true,
    secure: env.cookieSecure,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE_S,
  });
  return response;
}

async function readCredentials(request: NextRequest): Promise<{ password: string; next: string }> {
  const type = request.headers.get("content-type") ?? "";
  if (type.includes("application/json")) {
    const body: unknown = await request.json().catch(() => ({}));
    const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
    return { password: String(record.password ?? ""), next: String(record.next ?? "/") };
  }
  const form = await request.formData().catch(() => new FormData());
  return { password: String(form.get("password") ?? ""), next: String(form.get("next") ?? "/") };
}
