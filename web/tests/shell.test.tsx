import { screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/features/shell/components/sidebar";
import { TabBar } from "@/features/shell/components/tab-bar";
import { isActive, visibleNav } from "@/features/shell/nav";
import { violations } from "./support/axe";
import { renderWithIntl } from "./support/intl";

const path = vi.hoisted(() => ({ current: "/training/workout/3" }));
vi.mock("next/navigation", () => ({ usePathname: () => path.current }));

describe("app shell (P8.12)", () => {
  it("the phone tab bar has the five sections and marks the current one", () => {
    renderWithIntl(<TabBar />, "tr");
    const nav = screen.getByRole("navigation", { name: "Ana menü" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "Bugün",
      "Antrenman",
      "Beslenme",
      "İlerleme",
      "Ben",
    ]);
    expect(within(nav).getByRole("link", { name: "Antrenman" })).toHaveAttribute("aria-current", "page");
  });

  it("only the owner sees the admin entry", () => {
    const { rerender } = renderWithIntl(<Sidebar isOwner={false} name="Ayşe" />);
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
    rerender(<Sidebar isOwner name="Owner" />);
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute("href", "/admin");
    expect(visibleNav(false).some((item) => item.ownerOnly)).toBe(false);
  });

  it("matches sections by path segment", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/training")).toBe(false);
    expect(isActive("/training", "/training/history")).toBe(true);
    expect(isActive("/training", "/trainings")).toBe(false);
  });

  it("has no axe violations", async () => {
    path.current = "/";
    expect(await violations(<TabBar />)).toEqual([]);
  });
});
