import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/** Liveness for the container healthcheck; public and reveals nothing. */
export function GET(): NextResponse {
  return NextResponse.json({ status: "ok" });
}
