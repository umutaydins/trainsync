import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PeriodSwitcher } from "@/features/progress/components/period-switcher";
import { defaultBucket, parsePeriod, progressHref, rangeError } from "@/features/progress/types";
import { renderWithIntl } from "./support/intl";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/progress" }));

/** Phone width and reduced motion (no count-up), so the sheet is a drawer. */
function stubMedia(desktop = false) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("reduce") || (desktop && query.includes("min-width")),
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

beforeEach(() => {
  push.mockClear();
  stubMedia(true);
});

describe("period in the URL", () => {
  it("parses a valid period and falls back to this month", () => {
    expect(parsePeriod({ period: "3m" })).toEqual({ period: "3m" });
    expect(parsePeriod({})).toEqual({ period: "month" });
    expect(parsePeriod({ period: "decade" }).period).toBe("month");
    expect(parsePeriod({ period: ["year", "week"] }).period).toBe("year");
  });

  it("keeps a custom range only when both days are valid and in order", () => {
    expect(parsePeriod({ period: "custom", from: "2026-09-01", to: "2026-09-30" })).toEqual({ period: "custom", from: "2026-09-01", to: "2026-09-30" });
    expect(parsePeriod({ period: "custom", from: "2026-09-30", to: "2026-09-01" }).period).toBe("month");
    expect(parsePeriod({ period: "custom", from: "2026-02-30", to: "2026-03-01" }).period).toBe("month");
    expect(parsePeriod({ period: "custom" }).period).toBe("month");
  });

  it("reads the lift and the heatmap year, ignoring junk", () => {
    expect(parsePeriod({ period: "all", lift: "12", year: "2025" })).toEqual({ period: "all", lift: 12, year: 2025 });
    expect(parsePeriod({ lift: "x", year: "20" })).toEqual({ period: "month", lift: undefined, year: undefined });
  });

  it("builds shareable links", () => {
    expect(progressHref({ period: "week" })).toBe("/progress?period=week");
    expect(progressHref({ period: "custom", from: "2026-09-01", to: "2026-09-30", lift: 3 })).toBe(
      "/progress?period=custom&from=2026-09-01&to=2026-09-30&lift=3",
    );
    expect(progressHref({ period: "year", from: "2026-01-01", to: "2026-02-01" })).toBe("/progress?period=year");
  });

  it("validates a custom range", () => {
    expect(rangeError("2026-09-01", "2026-09-01")).toBeNull();
    expect(rangeError("", "2026-09-01")).toBe("missing");
    expect(rangeError("2026-10-02", "2026-10-01")).toBe("order");
  });

  it("knows the API's default bucket", () => {
    expect(defaultBucket(31)).toBe("day");
    expect(defaultBucket(32)).toBe("week");
    expect(defaultBucket(184)).toBe("month");
  });
});

describe("period switcher", () => {
  it("marks the current period and pushes the new one, keeping the lift", async () => {
    const user = userEvent.setup();
    renderWithIntl(<PeriodSwitcher query={{ period: "month", lift: 3 }} today="2026-10-19" />);
    expect(screen.getByRole("radio", { name: "This month" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: "Last 3 months" }));
    expect(push).toHaveBeenCalledWith("/progress?period=3m&lift=3", { scroll: false });
  });

  it("speaks Turkish", () => {
    renderWithIntl(<PeriodSwitcher query={{ period: "all" }} today="2026-10-19" />, "tr");
    expect(screen.getByRole("radio", { name: "Tüm zamanlar" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Bu hafta" })).toHaveTextContent("H");
  });

  it("opens the custom sheet, rejects a reversed range, then applies a valid one", async () => {
    const user = userEvent.setup();
    renderWithIntl(<PeriodSwitcher query={{ period: "month" }} today="2026-10-19" />);
    await user.click(screen.getByRole("radio", { name: "Custom range" }));
    const dialog = await screen.findByRole("dialog", { name: "Custom range" });
    expect(dialog).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show this range" }));
    expect(screen.getByText("Pick both days.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("From"), "2026-10-15");
    await user.clear(screen.getByLabelText("To"));
    await user.type(screen.getByLabelText("To"), "2026-10-01");
    await user.click(screen.getByRole("button", { name: "Show this range" }));
    expect(screen.getByText("The first day must be on or before the last day.")).toBeInTheDocument();
    expect(screen.getByLabelText("To")).toHaveAttribute("aria-invalid", "true");
    expect(push).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("To"));
    await user.type(screen.getByLabelText("To"), "2026-10-18");
    await user.click(screen.getByRole("button", { name: "Show this range" }));
    expect(push).toHaveBeenCalledWith("/progress?period=custom&from=2026-10-15&to=2026-10-18", { scroll: false });
  });

  it("lets a custom range be edited (the active segment cannot be clicked again)", async () => {
    const user = userEvent.setup();
    renderWithIntl(<PeriodSwitcher query={{ period: "custom", from: "2026-09-01", to: "2026-09-30" }} today="2026-10-19" />);
    await user.click(screen.getByRole("button", { name: "Change range" }));
    expect(await screen.findByLabelText("From")).toHaveValue("2026-09-01");
  });
});
