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

  it("a responsive grid starts from a one-column template that may shrink (no sideways scroll on phones)", () => {
    // `grid md:grid-cols-2` alone sizes its single phone column to the content: a long truncated
    // line then pushes the page wider than the screen. `grid-cols-1` is minmax(0, 1fr).
    const grid = /className="grid ([^"]*)"/g;
    const responsive = (classes: string[]) => classes.some((c) => /^(sm|md|lg|xl):grid-cols-/.test(c));
    const base = (classes: string[]) => classes.some((c) => c.startsWith("grid-cols-"));
    const offenders = files(src)
      .filter((path) => path.endsWith(".tsx"))
      .flatMap((path) => [...readFileSync(path, "utf8").matchAll(grid)].map((match) => ({ path, classes: match[1]!.split(/\s+/) })))
      .filter(({ classes }) => responsive(classes) && !base(classes))
      .map(({ path, classes }) => `${path.slice(src.length + 1)}: grid ${classes.join(" ")}`);
    expect(offenders).toEqual([]);
  });

  it("ok, warn and bad text stay readable on their soft tint in the light theme (WCAG AA)", () => {
    const css = readFileSync(join(src, "styles/tokens.css"), "utf8");
    const light = css.slice(css.indexOf("html.light {"), css.indexOf("}", css.indexOf("html.light {")));
    const token = (name: string) => {
      const value = new RegExp(`--${name}: ([^;]+);`).exec(light)?.[1];
      if (!value) throw new Error(`no --${name} in html.light`);
      return value;
    };
    for (const tone of ["ok", "warn", "bad"]) {
      const text = hex(token(tone));
      const alpha = Number(/\/ ([\d.]+)\)/.exec(token(`${tone}-soft`))?.[1]);
      for (const surface of ["surface", "surface-2", "surface-3"]) {
        const background = blend(text, alpha, hex(token(surface)));
        expect(contrast(text, background), `${tone} on ${tone}-soft over ${surface}`).toBeGreaterThanOrEqual(AA_TEXT);
      }
    }
  });
});

const AA_TEXT = 4.5;
type Rgb = [number, number, number];

function hex(value: string): Rgb {
  const digits = value.trim().replace("#", "");
  return [0, 2, 4].map((at) => parseInt(digits.slice(at, at + 2), 16)) as Rgb;
}

function blend(top: Rgb, alpha: number, under: Rgb): Rgb {
  return top.map((channel, i) => channel * alpha + under[i]! * (1 - alpha)) as Rgb;
}

function luminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map((channel) => {
    const v = channel / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  }) as Rgb;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: Rgb, b: Rgb): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (light + 0.05) / (dark + 0.05);
}
