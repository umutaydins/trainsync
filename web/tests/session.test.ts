// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  SESSION_MAX_AGE_S,
  createSessionToken,
  passwordMatches,
  safeNextPath,
  verifySessionToken,
} from "@/lib/session";

const SECRET = "s".repeat(40);
const NOW = new Date("2026-10-18T12:00:00Z");

describe("session token", () => {
  it("verifies a fresh token", () => {
    expect(verifySessionToken(createSessionToken(SECRET, NOW), SECRET, NOW)).toBe(true);
  });

  it("expires after 7 days", () => {
    const token = createSessionToken(SECRET, NOW);
    const justBefore = new Date(NOW.getTime() + (SESSION_MAX_AGE_S - 1) * 1000);
    const after = new Date(NOW.getTime() + SESSION_MAX_AGE_S * 1000);
    expect(verifySessionToken(token, SECRET, justBefore)).toBe(true);
    expect(verifySessionToken(token, SECRET, after)).toBe(false);
  });

  it("rejects another secret, a tampered expiry and garbage", () => {
    const token = createSessionToken(SECRET, NOW);
    const [expiresAt, signature] = token.split(".");
    expect(verifySessionToken(token, "x".repeat(40), NOW)).toBe(false);
    expect(verifySessionToken(`${Number(expiresAt) + 999}.${signature}`, SECRET, NOW)).toBe(false);
    for (const bad of [undefined, "", "abc", `${expiresAt}.`, `.${signature}`, `${token}x`]) {
      expect(verifySessionToken(bad, SECRET, NOW)).toBe(false);
    }
  });
});

describe("passwordMatches", () => {
  it("matches only the exact password", () => {
    expect(passwordMatches("hunter2", "hunter2")).toBe(true);
    expect(passwordMatches("hunter3", "hunter2")).toBe(false);
    expect(passwordMatches("", "hunter2")).toBe(false);
    expect(passwordMatches("hunter2 but much longer", "hunter2")).toBe(false);
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
