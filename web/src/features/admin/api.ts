import "server-only";

import { notFound } from "next/navigation";

import type { AdminUserList, InviteList } from "@/features/admin/types";
import { api, getJson, load, type Loaded } from "@/lib/api";
import type { Me } from "@/lib/types";

/**
 * The owner's pages exist for the owner only: anyone else gets the not-found page (ADR 0034), so
 * the admin area is not even confirmed to exist. When the API cannot say who is asking, the page
 * shows its error state instead.
 */
export async function ownerOnly(): Promise<Loaded<Me>> {
  const me = await load(api.me);
  if (me.ok && me.data.role !== "owner") notFound();
  return me;
}

export const adminApi = {
  invites: () => getJson<InviteList>("/v1/admin/invites"),
  users: () => getJson<AdminUserList>("/v1/admin/users"),
};
