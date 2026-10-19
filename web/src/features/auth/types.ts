import type { components } from "@/lib/api-types";

type Schemas = components["schemas"];

export type RegistrationMode = Schemas["RegistrationOut"]["mode"];
export type RegisterIn = Schemas["RegisterIn"];
