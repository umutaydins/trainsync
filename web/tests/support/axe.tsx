import axe from "axe-core";
import type { ReactElement } from "react";

import type { Locale } from "@/i18n/config";
import { renderWithIntl } from "./intl";

/** axe violations of `ui` rendered in a `<main>` with the messages of `locale`. */
export async function violations(ui: ReactElement, locale: Locale = "en"): Promise<string[]> {
  const { container } = renderWithIntl(<main>{ui}</main>, locale);
  const result = await axe.run(container, {
    // jsdom cannot compute colours; contrast is covered by the design tokens.
    rules: { "color-contrast": { enabled: false } },
  });
  return result.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}
