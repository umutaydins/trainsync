import { NextResponse, type NextRequest } from "next/server";

import { startSession } from "@/lib/auth";
import { clientIp, loginLimiter } from "@/lib/login-limit";
import { safeNextPath, seeOther } from "@/lib/session";
import { authRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

/**
 * Form or JSON body `{email, password, next?}`, checked by the API (`POST /v1/auth/login`). 303 to
 * `next` with the session cookie, or the API's 401 / 429. This BFF also limits failures per
 * browser address (LOGIN_MAX_FAILURES in LOGIN_WINDOW_MS) in front of the API's own limits,
 * because the API only sees the BFF's address.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const ip = clientIp(request.headers);
  const retryAfter = loginLimiter.retryAfterS(ip);
  if (retryAfter !== null) return tooMany(String(retryAfter));
  const { email, password, next } = await readCredentials(request);
  const result = await authRequest(
    "POST",
    "/v1/auth/login",
    JSON.stringify({ email, password }),
    { "User-Agent": request.headers.get("user-agent") ?? "" },
  );
  if (!result.ok) {
    if (result.status === 401) loginLimiter.recordFailure(ip);
    if (result.status === 429) return tooMany(result.retryAfter ?? "900");
    return NextResponse.json({ error: result.error }, { status: result.status });
  }
  loginLimiter.reset(ip);
  const token = (result.data as { token?: unknown }).token;
  if (typeof token !== "string") return NextResponse.json({ error: "sign-in failed" }, { status: 502 });
  const response = new NextResponse(null, seeOther(safeNextPath(next)));
  startSession(response, token);
  return response;
}

function tooMany(retryAfter: string): NextResponse {
  return NextResponse.json(
    { error: "too many failed attempts" },
    { status: 429, headers: { "Retry-After": retryAfter } },
  );
}

async function readCredentials(
  request: NextRequest,
): Promise<{ email: string; password: string; next: string }> {
  const type = request.headers.get("content-type") ?? "";
  if (type.includes("application/json")) {
    const body: unknown = await request.json().catch(() => ({}));
    const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
    return {
      email: String(record.email ?? ""),
      password: String(record.password ?? ""),
      next: String(record.next ?? "/"),
    };
  }
  const form = await request.formData().catch(() => new FormData());
  return {
    email: String(form.get("email") ?? ""),
    password: String(form.get("password") ?? ""),
    next: String(form.get("next") ?? "/"),
  };
}
