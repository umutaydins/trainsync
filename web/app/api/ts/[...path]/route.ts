import { NextResponse, type NextRequest } from "next/server";

import { checkCsrf } from "@/lib/csrf";
import { CSRF_COOKIE } from "@/lib/csrf-cookie";
import { serverEnv } from "@/lib/env";
import {
  MAX_BODY_BYTES,
  allowedMethods,
  upstreamRequest,
  type Method,
  type UpstreamResult,
} from "@/lib/upstream";

export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

type Context = { params: Promise<{ path: string[] }> };

/**
 * BFF: the browser calls /api/ts/v1/..., this handler adds the API key server-side and forwards
 * allowlisted method + path combinations only (lib/upstream.ts, ADR 0011). Mutations also need
 * a same-origin `Origin`/`Referer`, the CSRF double-submit token, a JSON body of at most
 * MAX_BODY_BYTES. Upstream errors become `{error}` (plus `detail` for mutations) with the
 * upstream status; upstream headers are never passed on.
 */
async function handle(method: Method, request: NextRequest, { params }: Context): Promise<NextResponse> {
  const { path } = await params;
  const target = `/${path.join("/")}`;
  const allowed = allowedMethods(target);
  if (!allowed) return error(404, "not found");
  if (!allowed.includes(method)) {
    return error(405, "method not allowed", { Allow: allowed.join(", ") });
  }
  const search = request.nextUrl.searchParams;
  if (method === "GET") return reply(await upstreamRequest("GET", target, search, null), false);

  const failure = checkCsrf(
    request.headers,
    request.cookies.get(CSRF_COOKIE)?.value,
    serverEnv().publicWebUrl,
  );
  if (failure === "origin") return error(403, "cross-origin request refused");
  if (failure === "token") return error(403, "missing or invalid CSRF token");

  const body = await readJsonBody(request, method);
  if (!body.ok) return error(body.status, body.error);
  return reply(await upstreamRequest(method, target, search, body.text), true);
}

type Body = { ok: true; text: string | null } | { ok: false; status: number; error: string };

/**
 * POST/PUT need `Content-Type: application/json`; DELETE may come without a body. The body is
 * read with a byte cap (Content-Length is only a hint) and must parse as JSON.
 */
async function readJsonBody(request: NextRequest, method: Method): Promise<Body> {
  const type = request.headers.get("content-type");
  const isJson = type !== null && /^application\/json\s*(?:;|$)/i.test(type.trim());
  // DELETE without a content type is fine as long as it has no body (checked after reading).
  if (!isJson && !(method === "DELETE" && type === null)) return unsupportedType();

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) return tooLarge();
  const text = await readCapped(request.body, MAX_BODY_BYTES);
  if (text === null) return tooLarge();
  if (text.trim() === "") return { ok: true, text: null };
  if (!isJson) return unsupportedType();
  try {
    JSON.parse(text);
  } catch {
    return { ok: false, status: 400, error: "invalid JSON body" };
  }
  return { ok: true, text };
}

function unsupportedType(): Body {
  return { ok: false, status: 415, error: "content type must be application/json" };
}

function tooLarge(): Body {
  return { ok: false, status: 413, error: `body larger than ${MAX_BODY_BYTES} bytes` };
}

/** The stream as UTF-8 text, or null as soon as it exceeds `limit` bytes (reading stops there). */
async function readCapped(stream: ReadableStream<Uint8Array> | null, limit: number): Promise<string | null> {
  if (!stream) return "";
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel().catch(() => undefined);
      return null;
    }
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function reply(result: UpstreamResult, isMutation: boolean): NextResponse {
  if (!result.ok) {
    const body =
      isMutation && result.detail !== undefined
        ? { error: result.error, detail: result.detail }
        : { error: result.error };
    return NextResponse.json(body, { status: result.status, headers: NO_STORE });
  }
  if (result.status === 204 || result.status === 205 || result.status === 304) {
    return new NextResponse(null, { status: result.status, headers: NO_STORE });
  }
  return NextResponse.json(result.data, { status: result.status, headers: NO_STORE });
}

function error(status: number, message: string, headers: Record<string, string> = {}): NextResponse {
  return NextResponse.json({ error: message }, { status, headers: { ...NO_STORE, ...headers } });
}

export function GET(request: NextRequest, context: Context): Promise<NextResponse> {
  return handle("GET", request, context);
}

export function POST(request: NextRequest, context: Context): Promise<NextResponse> {
  return handle("POST", request, context);
}

export function PUT(request: NextRequest, context: Context): Promise<NextResponse> {
  return handle("PUT", request, context);
}

export function PATCH(request: NextRequest, context: Context): Promise<NextResponse> {
  return handle("PATCH", request, context);
}

export function DELETE(request: NextRequest, context: Context): Promise<NextResponse> {
  return handle("DELETE", request, context);
}
