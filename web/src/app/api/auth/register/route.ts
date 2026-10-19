import { NextResponse, type NextRequest } from "next/server";

import { startSession } from "@/lib/auth";
import { checkCsrfOrigin } from "@/lib/csrf";
import { serverEnv } from "@/lib/env";
import { clientIp, loginLimiter } from "@/lib/login-limit";
import { loadPreferences, rememberPreferences } from "@/lib/preferences";
import { safeNextPath, seeOther } from "@/lib/session";
import { authRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

const FIELDS = ["email", "password", "display_name", "timezone", "invite_code"] as const;

/**
 * JSON `{email, password, display_name?, timezone?, invite_code?, next?}` → `POST /v1/auth/register`,
 * then signs the new account in (303 to `next`). The API enforces REGISTRATION_MODE, invites and
 * its own limits; same-origin only, like every other write.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!checkCsrfOrigin(request.headers, serverEnv().allowedOrigins)) {
    return NextResponse.json({ error: "cross-origin request refused" }, { status: 403 });
  }
  const ip = clientIp(request.headers);
  if (loginLimiter.retryAfterS(ip) !== null) {
    return NextResponse.json({ error: "too many attempts" }, { status: 429 });
  }
  const body: unknown = await request.json().catch(() => null);
  const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const fields = Object.fromEntries(
    FIELDS.filter((name) => typeof record[name] === "string" && record[name] !== "").map(
      (name) => [name, record[name]],
    ),
  );
  const created = await authRequest("POST", "/v1/auth/register", JSON.stringify(fields));
  if (!created.ok) {
    return NextResponse.json(
      { error: created.error, detail: created.detail },
      { status: created.status },
    );
  }
  const login = await authRequest(
    "POST",
    "/v1/auth/login",
    JSON.stringify({ email: fields.email, password: fields.password }),
  );
  const token = login.ok ? (login.data as { token?: unknown }).token : null;
  if (typeof token !== "string") return NextResponse.json({ error: "sign-in failed" }, { status: 502 });
  const response = new NextResponse(null, seeOther(safeNextPath(String(record.next ?? "/"))));
  startSession(response, token);
  rememberPreferences(response, await loadPreferences(token));
  return response;
}
