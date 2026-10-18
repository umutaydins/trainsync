import { NextResponse } from "next/server";

import { SESSION_COOKIE, seeOther } from "@/lib/session";

export const dynamic = "force-dynamic";

export function POST(): NextResponse {
  const response = new NextResponse(null, seeOther("/login"));
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
