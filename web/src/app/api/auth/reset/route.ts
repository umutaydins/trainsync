import { NextResponse, type NextRequest } from "next/server";

import { checkCsrfOrigin } from "@/lib/csrf";
import { serverEnv } from "@/lib/env";
import { authRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

/** JSON `{token, password}` from an owner-generated reset link → `POST /v1/auth/reset`. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!checkCsrfOrigin(request.headers, serverEnv().allowedOrigins)) {
    return NextResponse.json({ error: "cross-origin request refused" }, { status: 403 });
  }
  const body: unknown = await request.json().catch(() => null);
  const record = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const result = await authRequest(
    "POST",
    "/v1/auth/reset",
    JSON.stringify({ token: String(record.token ?? ""), password: String(record.password ?? "") }),
  );
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
  return new NextResponse(null, { status: 204 });
}
