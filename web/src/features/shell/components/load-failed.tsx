import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { Failure } from "@/components/ui/states";

/** No answer at all (offline), or the BFF could not reach the API. */
const NO_ANSWER = 0;
const BAD_GATEWAY = 502;
const GATEWAY_TIMEOUT = 504;

/** Whether a failed read or write means the backend is not answering (not a refusal). */
export function isBackendDown(status: number): boolean {
  return status === NO_ANSWER || status === BAD_GATEWAY || status === GATEWAY_TIMEOUT;
}

/**
 * The error state of a block whose read failed. The API's own error text is an error code for
 * clients, not copy: the block says what failed and, when the backend is down, that it is.
 */
export function LoadFailed({ title, status, action }: { title: ReactNode; status: number; action?: ReactNode }) {
  const t = useTranslations("common.states");
  return <Failure title={title} message={isBackendDown(status) ? t("backendDown") : undefined} action={action} />;
}
