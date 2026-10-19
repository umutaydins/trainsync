// @vitest-environment node
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, it } from "vitest";

const web = fileURLToPath(new URL("..", import.meta.url));

it("src/lib/api-types.ts is up to date with docs/openapi.json (run `pnpm gen:api`)", () => {
  const dir = mkdtempSync(join(tmpdir(), "api-types-"));
  try {
    const out = join(dir, "api-types.ts");
    execFileSync(
      join(web, "node_modules/.bin/openapi-typescript"),
      [join(web, "../docs/openapi.json"), "-o", out],
      { cwd: web, stdio: "pipe" },
    );
    expect(readFileSync(join(web, "src/lib/api-types.ts"), "utf8")).toBe(readFileSync(out, "utf8"));
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}, 30_000);
