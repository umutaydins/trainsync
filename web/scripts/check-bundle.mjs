// Fails if a server secret that was set at build time appears in any browser-served file, or if
// code that sends the API key (the `X-API-Key` header name, lib/upstream.ts) was bundled for the
// browser: that would mean a client module reaches the upstream call path (ADR 0011).
// Usage (after `pnpm build` with the same env): node scripts/check-bundle.mjs
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const SECRETS = ["TRAINSYNC_API_KEY", "DASHBOARD_PASSWORD", "DASHBOARD_SESSION_SECRET"];
const ROOTS = [".next/static", "public"];
const SERVER_MARKERS = [/x-api-key/i];

const values = SECRETS.map((name) => [name, process.env[name] ?? ""]);
const missing = values.filter(([, value]) => value.length < 8).map(([name]) => name);
if (missing.length > 0) {
  console.error(`check-bundle: set ${missing.join(", ")} (>= 8 chars) to the values used at build time`);
  process.exit(2);
}

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* files(path);
    else yield path;
  }
}

let scanned = 0;
const leaks = [];
for (const root of ROOTS) {
  let entries;
  try {
    entries = [...files(root)];
  } catch {
    if (root === ".next/static") {
      console.error("check-bundle: .next/static not found, run `pnpm build` first");
      process.exit(2);
    }
    continue;
  }
  for (const path of entries) {
    const content = readFileSync(path);
    scanned += 1;
    for (const [name, value] of values) {
      if (content.includes(value)) leaks.push(`${name} in ${path}`);
    }
    const text = content.toString("latin1");
    for (const marker of SERVER_MARKERS) {
      if (marker.test(text)) leaks.push(`server-only code (${marker}) in ${path}`);
    }
  }
}

if (scanned === 0) {
  console.error("check-bundle: no client files scanned");
  process.exit(2);
}
if (leaks.length > 0) {
  console.error(`check-bundle: server secrets found in client files:\n  ${leaks.join("\n  ")}`);
  process.exit(1);
}
console.log(`check-bundle: OK (${scanned} client files, no server secrets or API-key code)`);
