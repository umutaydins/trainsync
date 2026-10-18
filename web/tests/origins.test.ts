// @vitest-environment node
import { describe, expect, it } from "vitest";

import { checkCsrf, createCsrfToken } from "@/lib/csrf";
import { allowedOrigins } from "@/lib/origins";

const PROD = "https://trainsync-umut.vercel.app";
const vercelEnv = {
  VERCEL_URL: "trainsync-3k9x2ab1c-umut-projects.vercel.app",
  VERCEL_BRANCH_URL: "trainsync-git-feature-x-umut-projects.vercel.app",
  VERCEL_PROJECT_PRODUCTION_URL: "trainsync-umut.vercel.app",
};

function headers(origin: string, token: string): Headers {
  return new Headers({ origin, "x-csrf-token": token });
}

describe("allowed origins (P7.6)", () => {
  it("are the public URL plus this deployment's own Vercel URLs", () => {
    expect(allowedOrigins(PROD, vercelEnv)).toEqual([
      PROD,
      "https://trainsync-3k9x2ab1c-umut-projects.vercel.app",
      "https://trainsync-git-feature-x-umut-projects.vercel.app",
    ]);
    expect(allowedOrigins("http://localhost:3000", {})).toEqual(["http://localhost:3000"]);
  });

  it("ignore anything in the Vercel variables that is not a bare hostname", () => {
    const odd = { VERCEL_URL: "https://evil.example", VERCEL_BRANCH_URL: "a.vercel.app/path", VERCEL_PROJECT_PRODUCTION_URL: "" };
    expect(allowedOrigins(PROD, odd)).toEqual([PROD]);
  });

  it.each([
    ["the production domain", PROD, true],
    ["this deployment's preview URL", "https://trainsync-3k9x2ab1c-umut-projects.vercel.app", true],
    ["this branch's preview URL", "https://trainsync-git-feature-x-umut-projects.vercel.app", true],
    ["another preview of the project", "https://trainsync-aaaaaaaaa-umut-projects.vercel.app", false],
    ["another project", "https://other-3k9x2ab1c-umut-projects.vercel.app", false],
    ["a lookalike suffix", "https://trainsync-umut.vercel.app.evil.example", false],
    ["a lookalike prefix", "https://eviltrainsync-umut.vercel.app", false],
    ["plain http", "http://trainsync-umut.vercel.app", false],
    ["another port", "https://trainsync-umut.vercel.app:8443", false],
  ])("CSRF origin check: %s → %s", (_what, origin, ok) => {
    const token = createCsrfToken();
    const failure = checkCsrf(headers(origin, token), token, allowedOrigins(PROD, vercelEnv));
    expect(failure).toBe(ok ? null : "origin");
  });
});
