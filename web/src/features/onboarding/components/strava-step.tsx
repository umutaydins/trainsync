"use client";

import { CircleCheck, CircleDashed, CircleAlert } from "lucide-react";
import Image from "next/image";
import { useFormatter, useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { StepFrame, type StepProps } from "@/features/onboarding/components/step-frame";
import type { StravaConnection, StravaReturn } from "@/features/onboarding/types";

/** The BFF route that sends the browser to Strava and has it come back here. */
export const STRAVA_CONNECT_HREF = "/api/strava/connect?return_to=/onboarding";
/** Strava's official button and attribution (developers.strava.com/guidelines, unmodified). */
const CONNECT_BUTTON = { src: "/strava/btn_strava_connect_with_orange.svg", width: 237, height: 48 } as const;
const POWERED_BY = { src: "/strava/api_logo_pwrdBy_strava_horiz_orange.svg", width: 365, height: 37 } as const;
const POWERED_BY_HEIGHT_PX = 18;

/** Connect Strava with the official button; the state comes from `GET /v1/me/strava`. */
export function StravaStep({
  onNext,
  connection,
  returned,
}: StepProps & { connection: StravaConnection | null; returned: StravaReturn }) {
  const t = useTranslations("onboarding");
  const format = useFormatter();
  const connected = connection?.connected === true;
  const failure = returned && "error" in returned ? returned.error : null;
  return (
    <StepFrame
      title={t("strava.title")}
      body={t("strava.body")}
      action={
        connected ? (
          <Button type="button" size="lg" block onClick={onNext}>
            {t("continue")}
          </Button>
        ) : null
      }
    >
      <div role="status" className="flex items-start gap-3 rounded-card border border-border bg-surface p-4">
        {connected ? (
          <CircleCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-ok" />
        ) : failure ? (
          <CircleAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-bad" />
        ) : (
          <CircleDashed aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" />
        )}
        <div className="text-sm">
          <p className="font-semibold">{connected ? t("strava.connected") : t("strava.notConnected")}</p>
          {connected && connection?.connected_at ? (
            <p className="mt-0.5 text-muted">
              {t("strava.connectedSince", { date: format.dateTime(new Date(connection.connected_at), { dateStyle: "medium" }) })}
            </p>
          ) : null}
          {!connected && failure ? <p className="mt-0.5 text-bad">{t("strava.failed", { reason: failure })}</p> : null}
        </div>
      </div>
      {connected ? null : (
        // A full page navigation: the BFF answers with a redirect to strava.com.
        <a href={STRAVA_CONNECT_HREF} className="self-start rounded-[6px]">
          <Image
            src={CONNECT_BUTTON.src}
            width={CONNECT_BUTTON.width}
            height={CONNECT_BUTTON.height}
            alt={t("strava.connectLabel")}
            unoptimized
            priority
          />
        </a>
      )}
      <Image
        src={POWERED_BY.src}
        width={POWERED_BY.width}
        height={POWERED_BY.height}
        alt={t("strava.poweredBy")}
        unoptimized
        style={{ height: POWERED_BY_HEIGHT_PX, width: "auto" }}
      />
    </StepFrame>
  );
}
