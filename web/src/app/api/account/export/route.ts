import { NextResponse, type NextRequest } from "next/server";

import { tokenFromCookie } from "@/lib/auth";
import { SESSION_COOKIE, seeOther } from "@/lib/session";
import { upstreamGet } from "@/lib/upstream";

export const dynamic = "force-dynamic";

/** `trainsync-export-2026-10-19.json` (the UTC date of the download). */
function exportFileName(now: Date): string {
  return `trainsync-export-${now.toISOString().slice(0, 10)}.json`;
}

/**
 * Me → Data → Export: every row of the account (`GET /v1/me/export`, ADR 0037) as a file download.
 * Without a valid session the browser goes to the sign-in page.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = tokenFromCookie(request.cookies.get(SESSION_COOKIE)?.value);
  const result = await upstreamGet("/v1/me/export", new URLSearchParams(), token);
  if (!result.ok && result.status === 401) return new NextResponse(null, seeOther("/login"));
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status, headers: { "Cache-Control": "no-store" } });
  }
  return new NextResponse(JSON.stringify(result.data, null, 2), {
    status: 200,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Content-Disposition": `attachment; filename="${exportFileName(new Date())}"`,
      "Cache-Control": "no-store",
    },
  });
}
