import {
  Activity,
  ChartNoAxesColumn,
  Dumbbell,
  RefreshCw,
  ShieldCheck,
  Sun,
  User,
  UtensilsCrossed,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Message key in the `nav` namespace. */
export type NavKey = "today" | "workout" | "food" | "progress" | "me" | "activities" | "sync" | "admin";

export interface NavItem {
  key: NavKey;
  href: string;
  icon: LucideIcon;
  /** In the phone's bottom tab bar (five at most); the rest are in the desktop sidebar only. */
  tab: boolean;
  ownerOnly?: boolean;
}

export const NAV: readonly NavItem[] = [
  { key: "today", href: "/", icon: Sun, tab: true },
  { key: "workout", href: "/training", icon: Dumbbell, tab: true },
  { key: "food", href: "/nutrition", icon: UtensilsCrossed, tab: true },
  { key: "progress", href: "/progress", icon: ChartNoAxesColumn, tab: true },
  { key: "me", href: "/me", icon: User, tab: true },
  { key: "activities", href: "/activities", icon: Activity, tab: false },
  { key: "sync", href: "/sync", icon: RefreshCw, tab: false },
  { key: "admin", href: "/admin", icon: ShieldCheck, tab: false, ownerOnly: true },
];

export function visibleNav(isOwner: boolean): NavItem[] {
  return NAV.filter((item) => !item.ownerOnly || isOwner);
}

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
