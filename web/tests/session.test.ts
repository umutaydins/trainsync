// @vitest-environment node
import { describe, expect, it } from "vitest";

import { SESSION_MAX_AGE_S, openSession, safeNextPath, sealSession } from "@/lib/session";

const SECRET = "s".repeat(40);
const NOW = new Date("2026-10-18T12:00:00Z");
const EXPIRES = Math.floor(NOW.getTime() / 1000) + 3600;

describe("sealed session cookie (ADR 0034)", () => {
  it("opens to the token it sealed, and only until it expires", () => {
    const value = sealSession({ token: "api-token", expiresAt: EXPIRES }, SECRET);
    expect(openSession(value, SECRET, NOW)).toEqual({ token: "api-token", expiresAt: EXPIRES });
    expect(openSession(value, SECRET, new Date((EXPIRES + 1) * 1000))).toBeNull();
    expect(value).not.toContain("api-token");
  });

  it("is different every time (random IV) and never outlives the API session cap", () => {
    const a = sealSession({ token: "t", expiresAt: EXPIRES }, SECRET);
    const b = sealSession({ token: "t", expiresAt: EXPIRES }, SECRET);
    expect(a).not.toBe(b);
    expect(SESSION_MAX_AGE_S).toBe(90 * 24 * 60 * 60);
  });

  it("refuses another secret, any tampering and garbage", () => {
    const value = sealSession({ token: "t", expiresAt: EXPIRES }, SECRET);
    expect(openSession(value, "x".repeat(40), NOW)).toBeNull();
    const [version, iv, sealed] = value.split(".");
    const flipped = `${sealed?.startsWith("A") ? "B" : "A"}${sealed?.slice(1)}`;
    for (const bad of [
      undefined,
      "",
      "garbage",
      `v1.${iv}.${sealed}`,
      `${version}.${iv}.${flipped}`,
      `${version}.${iv}`,
      `${value}.extra`,
    ]) {
      expect(openSession(bad, SECRET, NOW)).toBeNull();
    }
    expect(openSession(value, "", NOW)).toBeNull();
  });
});

describe("safeNextPath", () => {
  it.each([
    ["/activities?sport_type=Run", "/activities?sport_type=Run"],
    ["/sync", "/sync"],
    [undefined, "/"],
    ["https://evil.example", "/"],
    ["//evil.example", "/"],
    ["/\\evil.example", "/"],
    ["/login", "/"],
    ["/api/ts/v1/activities", "/"],
  ])("%s -> %s", (input, expected) => {
    expect(safeNextPath(input)).toBe(expected);
  });
});
