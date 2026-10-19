import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { DEV_ONLY_WEB_SECRETS, devSecretsInUse, warnDevSecrets } from "@/lib/dev-defaults";

// The dev values come from the compose file only; the code finds them by their `dev-` label.
const compose = readFileSync(resolve(__dirname, "../../docker-compose.yml"), "utf8");
const defaults: Record<string, string> = Object.fromEntries(
  [...compose.matchAll(/\$\{([A-Z0-9_]+):-([^}]*)\}/g)].map((m) => [m[1], m[2]]),
);
const devEnv: Record<string, string> = { NODE_ENV: "production" };
for (const name of DEV_ONLY_WEB_SECRETS) devEnv[name] = defaults[name]!;

describe("dev-only web secrets", () => {
  it("are overridable compose defaults labelled dev-", () => {
    for (const name of DEV_ONLY_WEB_SECRETS) expect(defaults[name], name).toMatch(/^dev-/);
  });

  it("are detected by name", () => {
    expect(devSecretsInUse(devEnv)).toEqual([...DEV_ONLY_WEB_SECRETS]);
    expect(devSecretsInUse({ ...devEnv, DASHBOARD_SESSION_SECRET: "my own" })).not.toContain(
      "DASHBOARD_SESSION_SECRET",
    );
  });

  it("warn in production with names, never values", () => {
    const warn = vi.fn();
    expect(warnDevSecrets(devEnv, warn)).toHaveLength(DEV_ONLY_WEB_SECRETS.length);
    expect(warn).toHaveBeenCalledTimes(1);
    const message = String(warn.mock.calls[0]![0]);
    expect(message).toContain("DASHBOARD_SESSION_SECRET");
    for (const name of DEV_ONLY_WEB_SECRETS) expect(message).not.toContain(devEnv[name]);
  });

  it("stay quiet outside production or with own values", () => {
    const warn = vi.fn();
    expect(warnDevSecrets({ ...devEnv, NODE_ENV: "development" }, warn)).toEqual([]);
    const own = { NODE_ENV: "production", DASHBOARD_SESSION_SECRET: "s".repeat(40) };
    expect(warnDevSecrets(own, warn)).toEqual([]);
    expect(warn).not.toHaveBeenCalled();
  });
});
