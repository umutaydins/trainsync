import { NextResponse, type NextRequest } from "next/server";

import { endSession, tokenFromCookie } from "@/lib/auth";
import { SESSION_COOKIE, seeOther } from "@/lib/session";
import { authRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

/** Revokes the API session (best effort), clears the cookies and goes to the sign-in page. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = tokenFromCookie(request.cookies.get(SESSION_COOKIE)?.value);
  if (token) {
    await authRequest("POST", "/v1/auth/logout", null, { Authorization: `Bearer ${token}` });
  }
  const response = new NextResponse(null, seeOther("/login"));
  endSession(response);
  return response;
}
