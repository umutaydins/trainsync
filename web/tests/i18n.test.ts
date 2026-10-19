// @vitest-environment node
import { describe, expect, it } from "vitest";

import { LOCALES, isLocale, isTimeZone, negotiate } from "@/i18n/config";
import { NAMESPACES, loadMessages } from "@/i18n/messages";

function keys(value: unknown, prefix = ""): string[] {
  if (value === null || typeof value !== "object") return [prefix];
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key));
}

describe("messages (ADR 0039)", () => {
  it("every language has the same keys in every namespace, and no empty text", async () => {
    const [en, ...others] = await Promise.all(LOCALES.map((locale) => loadMessages(locale)));
    for (const namespace of NAMESPACES) {
      const reference = keys(en![namespace]).sort();
      for (const messages of others) expect(keys(messages[namespace]).sort(), namespace).toEqual(reference);
    }
    for (const messages of [en!, ...others]) {
      const texts = JSON.stringify(messages);
      expect(texts).not.toMatch(/:""/);
    }
  });
});

describe("locale and time zone", () => {
  it.each([
    ["tr-TR,tr;q=0.9,en;q=0.8", "tr"],
    ["de-DE,de;q=0.9,tr;q=0.5", "tr"],
    ["en-US,en;q=0.9", "en"],
    ["fr", "en"],
    ["", "en"],
    [null, "en"],
    ["en;q=0.2, tr;q=0.8", "tr"],
  ])("Accept-Language %s -> %s", (header, locale) => {
    expect(negotiate(header)).toBe(locale);
  });

  it("knows its locales and real zones only", () => {
    expect(isLocale("tr")).toBe(true);
    expect(isLocale("de")).toBe(false);
    expect(isTimeZone("Europe/Istanbul")).toBe(true);
    expect(isTimeZone("Mars/Base")).toBe(false);
    expect(isTimeZone(undefined)).toBe(false);
  });
});
