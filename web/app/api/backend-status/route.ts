import { NextResponse } from "next/server";

import { backendReachable } from "@/lib/backend-status";

export const dynamic = "force-dynamic";

/** `{reachable}` for the error page (behind the login like every other route). */
export async function GET(): Promise<NextResponse> {
  return NextResponse.json({ reachable: await backendReachable() }, { headers: { "Cache-Control": "no-store" } });
}
