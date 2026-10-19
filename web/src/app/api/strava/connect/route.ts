import { NextResponse, type NextRequest } from "next/server";

import { tokenFromCookie } from "@/lib/auth";
import { serverEnv } from "@/lib/env";
import { SESSION_COOKIE, seeOther } from "@/lib/session";
import { upstreamRequest } from "@/lib/upstream";

export const dynamic = "force-dynamic";

const DEFAULT_RETURN_PATH = "/sync";
/**
 * Pages Strava may send the browser back to (`?return_to=`). Each must also be in the API's
 * OAUTH_RETURN_TO_ALLOWLIST as `<WEB_PUBLIC_URL><path>`, else the API ignores it.
 */
const RETURN_PATHS: readonly string[] = [DEFAULT_RETURN_PATH, "/onboarding"];

/**
 * "Connect with Strava": asks the API for the authorize URL, whose signed state names the signed-in
 * user (ADR 0037), and sends the browser there. Strava redirects back to the API's callback, which
 * returns the browser to the allowlisted `return_to` page (`/sync` by default).
 */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const requested = request.nextUrl.searchParams.get("return_to") ?? "";
  const returnPath = RETURN_PATHS.includes(requested) ? requested : DEFAULT_RETURN_PATH;
  const token = tokenFromCookie(request.cookies.get(SESSION_COOKIE)?.value);
  const search = new URLSearchParams({ return_to: `${serverEnv().publicWebUrl}${returnPath}` });
  const result = await upstreamRequest("POST", "/v1/me/strava/authorize-url", search, null, token);
  if (!result.ok) return new NextResponse(null, seeOther(result.status === 401 ? "/login" : returnPath));
  const { url } = result.data as { url: string };
  return NextResponse.redirect(url, 303);
}
