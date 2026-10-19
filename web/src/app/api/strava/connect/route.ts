import { NextResponse, type NextRequest } from "next/server";

import { tokenFromCookie } from "@/lib/auth";
import { serverEnv } from "@/lib/env";
import { SESSION_COOKIE, seeOther } from "@/lib/session";
import { upstreamRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

const RETURN_PATH = "/sync";

/**
 * "Connect with Strava": asks the API for the authorize URL, whose signed state names the signed-in
 * user (ADR 0037), and sends the browser there. Strava redirects back to the API's callback, which
 * returns the browser to `/sync`.
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const token = tokenFromCookie(request.cookies.get(SESSION_COOKIE)?.value);
  const search = new URLSearchParams({ return_to: `${serverEnv().publicWebUrl}${RETURN_PATH}` });
  const result = await upstreamRequest("POST", "/v1/me/strava/authorize-url", search, null, token);
  if (!result.ok) return new NextResponse(null, seeOther(result.status === 401 ? "/login" : RETURN_PATH));
  const { url } = result.data as { url: string };
  return NextResponse.redirect(url, 303);
}
