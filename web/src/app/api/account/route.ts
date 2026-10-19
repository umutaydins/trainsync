import { NextResponse, type NextRequest } from "next/server";

import { endSession, tokenFromCookie } from "@/lib/auth";
import { checkCsrf } from "@/lib/csrf";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { serverEnv } from "@/lib/env";
import { SESSION_COOKIE } from "@/lib/session";
import { upstreamRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

/**
 * Deletes the account (`DELETE /v1/me`, JSON `{password}`) and ends the browser session at once.
 * CSRF-checked like every mutation.
 */
export async function DELETE(request: NextRequest): Promise<NextResponse> {
  const failure = checkCsrf(
    request.headers,
    request.cookies.get(CSRF_COOKIE)?.value,
    serverEnv().allowedOrigins,
  );
  if (failure) return NextResponse.json({ error: "request refused" }, { status: 403 });
  const token = tokenFromCookie(request.cookies.get(SESSION_COOKIE)?.value);
  const body: unknown = await request.json().catch(() => null);
  const password = String((body as { password?: unknown } | null)?.password ?? "");
  const result = await upstreamRequest(
    "DELETE",
    "/v1/me",
    new URLSearchParams(),
    JSON.stringify({ password }),
    token,
  );
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
  const response = new NextResponse(null, { status: 204 });
  endSession(response);
  return response;
}
