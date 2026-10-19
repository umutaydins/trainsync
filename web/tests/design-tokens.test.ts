// @vitest-environment node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const src = fileURLToPath(new URL("../src", import.meta.url));
// Colours are defined once (ADR 0039); these files hold the definitions or need a literal colour
// outside CSS (the browser chrome, the PWA manifest).
const ALLOWED = new Set(["styles/tokens.css", "lib/theme.ts"]);
const COLOUR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/;

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

describe("design tokens", () => {
  it("no raw colour values outside the token files", () => {
    const offenders = files(src)
      .map((path) => path.slice(src.length + 1))
      .filter((path) => /\.(tsx?|css)$/.test(path) && !ALLOWED.has(path) && path !== "lib/api-types.ts")
      .filter((path) => COLOUR.test(readFileSync(join(src, path), "utf8")));
    expect(offenders).toEqual([]);
  });
});
