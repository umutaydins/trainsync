// @vitest-environment node
import { describe, expect, it } from "vitest";

import { checkCsrf, createCsrfToken, isCsrfToken } from "@/lib/csrf";

const ORIGIN = "https://dash.example.com";

function headers(values: Record<string, string>): Headers {
  return new Headers(values);
}

describe("CSRF tokens", () => {
  it("creates distinct well-formed tokens", () => {
    const tokens = new Set(Array.from({ length: 50 }, createCsrfToken));
    expect(tokens.size).toBe(50);
    for (const token of tokens) expect(isCsrfToken(token)).toBe(true);
  });

  it("rejects malformed tokens", () => {
    for (const value of [undefined, "", "abc", "x".repeat(44), `${"x".repeat(42)}=`]) {
      expect(isCsrfToken(value)).toBe(false);
    }
  });
});

describe("checkCsrf", () => {
  const token = createCsrfToken();

  it("passes with the same origin and matching tokens", () => {
    expect(checkCsrf(headers({ origin: ORIGIN, "x-csrf-token": token }), token, ORIGIN)).toBeNull();
    expect(
      checkCsrf(headers({ referer: `${ORIGIN}/training`, "x-csrf-token": token }), token, `${ORIGIN}/`),
    ).toBeNull();
  });

  it("checks the origin before the token", () => {
    expect(checkCsrf(headers({ origin: "https://evil.example" }), undefined, ORIGIN)).toBe("origin");
  });

  it("fails on token mismatch of equal or different length", () => {
    const other = createCsrfToken();
    expect(checkCsrf(headers({ origin: ORIGIN, "x-csrf-token": other }), token, ORIGIN)).toBe("token");
    expect(checkCsrf(headers({ origin: ORIGIN, "x-csrf-token": "x" }), token, ORIGIN)).toBe("token");
  });

  it("fails closed on an unparseable public origin", () => {
    expect(checkCsrf(headers({ origin: ORIGIN, "x-csrf-token": token }), token, "not a url")).toBe(
      "origin",
    );
  });
});
