import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Layer boundaries (ADR 0033, 0039): app/ routes compose features; features use lib, i18n and
// components/ui; lib and components/ui never reach up; i18n (messages, locale config) is a leaf.
const restrict = (...groups) => ({
  "no-restricted-imports": [
    "error",
    {
      patterns: groups.map((group) => ({
        group: [`@/${group}/*`, `@/${group}`],
        message: `no imports from ${group}/ here (layer boundary)`,
      })),
    },
  ],
});

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  { files: ["src/lib/**"], rules: restrict("app", "features", "components") },
  { files: ["src/components/ui/**"], rules: restrict("app", "features") },
  { files: ["src/features/**"], rules: restrict("app") },
  { files: ["src/i18n/**"], rules: restrict("app", "features", "components", "lib") },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "src/lib/api-types.ts",
    "playwright-report/**",
    "test-results/**",
  ]),
]);
