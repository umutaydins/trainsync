import { cookies, headers } from "next/headers";
import { getRequestConfig } from "next-intl/server";

import {
  DEFAULT_TIME_ZONE,
  LOCALE_COOKIE,
  TIME_ZONE_COOKIE,
  isLocale,
  isTimeZone,
  negotiate,
} from "@/i18n/config";
import { loadMessages } from "@/i18n/messages";

/** next-intl per request: the user's language and time zone from their cookies (ADR 0039). */
export default getRequestConfig(async () => {
  const jar = await cookies();
  const chosen = jar.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(chosen) ? chosen : negotiate((await headers()).get("accept-language"));
  const zone = jar.get(TIME_ZONE_COOKIE)?.value;
  return {
    locale,
    timeZone: isTimeZone(zone) ? zone : DEFAULT_TIME_ZONE,
    messages: await loadMessages(locale),
  };
});
