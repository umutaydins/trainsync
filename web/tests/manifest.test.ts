// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import manifest from "@/app/manifest";
import { config } from "@/proxy";

const web = fileURLToPath(new URL("..", import.meta.url));
const root = (path: string) => join(web, path);

describe("web app manifest", () => {
  const m = manifest();

  it("opens the training page standalone", () => {
    expect(m).toMatchObject({ name: "trainsync", short_name: "trainsync", start_url: "/training", display: "standalone" });
    // The accent design token.
    expect(readFileSync(root("src/styles/globals.css"), "utf8")).toContain(`--accent: ${m.theme_color};`);
  });

  it("lists icons that exist, including 192, 512 and a maskable one", () => {
    const icons = m.icons ?? [];
    for (const icon of icons) {
      const file = icon.src === "/icon.svg" ? root("src/app/icon.svg") : root(`public${icon.src}`);
      expect(existsSync(file), icon.src).toBe(true);
    }
    expect(icons.map((i) => `${i.sizes}:${i.purpose}`)).toEqual(
      expect.arrayContaining(["192x192:any", "512x512:any", "512x512:maskable"]),
    );
    const png = readFileSync(root("public/icons/icon-512.png"));
    expect(png.subarray(1, 4).toString()).toBe("PNG");
    expect(png.readUInt32BE(16)).toBe(512);
  });

  it("is served without a session (browsers fetch it without cookies)", () => {
    const matcher = new RegExp(`^${config.matcher[0]}$`);
    expect(matcher.test("/manifest.webmanifest")).toBe(false);
    expect(matcher.test("/icons/icon-192.png")).toBe(false);
    expect(matcher.test("/training")).toBe(true);
    expect(matcher.test("/api/ts/v1/training/programs")).toBe(true);
  });
});
