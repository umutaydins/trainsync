import { Database, KeyRound, Link2, Megaphone, ShieldCheck, UserRound } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/** Message key under `settings.sections`. */
export type SectionKey = "profile" | "security" | "coach" | "connections" | "data" | "admin";

export interface Section {
  key: SectionKey;
  href: string;
  icon: LucideIcon;
  ownerOnly?: boolean;
}

/** Me's sub-pages in order; Admin is listed for the owner only (on phones it is not in the tab bar). */
export const SECTIONS: readonly Section[] = [
  { key: "profile", href: "/me/profile", icon: UserRound },
  { key: "security", href: "/me/security", icon: KeyRound },
  { key: "coach", href: "/me/coach", icon: Megaphone },
  { key: "connections", href: "/me/connections", icon: Link2 },
  { key: "data", href: "/me/data", icon: Database },
  { key: "admin", href: "/admin", icon: ShieldCheck, ownerOnly: true },
];

export function visibleSections(isOwner: boolean): Section[] {
  return SECTIONS.filter((section) => !section.ownerOnly || isOwner);
}
