import { NextResponse, type NextRequest } from "next/server";

import { isAllowedPath, upstreamGet } from "@/lib/upstream";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

/**
 * BFF: the browser calls /api/ts/v1/..., this handler adds the API key server-side and forwards
 * GETs on allowlisted paths only. Upstream errors become `{error}` with the upstream status.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await params;
  const target = `/${path.join("/")}`;
  if (!isAllowedPath(target)) {
    return NextResponse.json({ error: "not found" }, { status: 404, headers: NO_STORE });
  }
  const result = await upstreamGet(target, request.nextUrl.searchParams);
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status, headers: NO_STORE });
  }
  return NextResponse.json(result.data, { status: result.status, headers: NO_STORE });
}

function methodNotAllowed(): NextResponse {
  return NextResponse.json(
    { error: "method not allowed" },
    { status: 405, headers: { ...NO_STORE, Allow: "GET" } },
  );
}

export const POST = methodNotAllowed;
export const PUT = methodNotAllowed;
export const PATCH = methodNotAllowed;
export const DELETE = methodNotAllowed;
