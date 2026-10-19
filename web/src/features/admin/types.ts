import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type Invite = Schemas["InviteOut"];
export type InviteCreated = Schemas["InviteCreated"];
export type InviteIn = Schemas["InviteIn"];
export type InviteList = Schemas["InviteList"];
export type InviteStatus = Invite["status"];
export type AdminUser = Schemas["AdminUserOut"];
export type AdminUserList = Schemas["AdminUserList"];
export type ResetLink = Schemas["ResetLinkOut"];
