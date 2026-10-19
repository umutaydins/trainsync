import { NextResponse } from "next/server";

import { authRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

/** How accounts are created (`invite` | `open` | `closed`): the register page hides the invite
 * field when it is `open`. */
export async function GET(): Promise<NextResponse> {
  const result = await authRequest("GET", "/v1/auth/registration", null);
  if (!result.ok) return NextResponse.json({ error: result.error }, { status: result.status });
  return NextResponse.json(result.data, { headers: { "Cache-Control": "no-store" } });
}
