"use client";

import { Flame, MessageSquareQuote, RefreshCw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ChoiceCards } from "@/features/onboarding/components/choice-cards";
import type { CoachPreview, Intensity, Profanity, Settings, Tone } from "@/features/onboarding/types";
import { bffGet } from "@/lib/bff-get";

export type Voice = Pick<Settings, "tone" | "intensity" | "profanity">;
type Preview = { state: "loading" } | { state: "ok"; line: CoachPreview } | { state: "failed" };

/**
 * The coach voice: tone, then intensity (hardcore only), then profanity (savage only), with a live
 * sample line from `GET /v1/me/coach-preview` in the current UI language. Onboarding and Me share it.
 */
export function VoicePicker({ voice, onChange }: { voice: Voice; onChange: (voice: Voice) => void }) {
  const t = useTranslations("onboarding.coach");
  const locale = useLocale();
  const [round, setRound] = useState(0);
  const preview = useCoachPreview(voice, locale, round);
  const hardcore = voice.tone === "hardcore";
  const savage = hardcore && voice.intensity === "savage";
  const set =
    <K extends keyof Voice>(key: K) =>
    (value: Voice[K]) =>
      onChange({ ...voice, [key]: value });

  return (
    <>
      <ChoiceCards<Tone>
        legend={t("tone")}
        name="tone"
        value={voice.tone}
        onChange={set("tone")}
        choices={[
          { value: "neutral", label: t("neutral"), hint: t("neutralHint") },
          { value: "hardcore", label: t("hardcore"), hint: t("hardcoreHint") },
        ]}
      />
      {hardcore ? (
        <ChoiceCards<Intensity>
          legend={t("intensity")}
          hint={t("intensityHint")}
          name="intensity"
          value={voice.intensity}
          onChange={set("intensity")}
          choices={[
            { value: "normal", label: t("normal"), hint: t("normalHint") },
            { value: "savage", label: t("savage"), hint: t("savageHint") },
          ]}
        />
      ) : null}
      {savage ? (
        <ChoiceCards<Profanity>
          legend={t("profanity")}
          hint={t("profanityHint")}
          name="profanity"
          value={voice.profanity}
          onChange={set("profanity")}
          choices={[
            { value: "roast", label: t("roast"), hint: t("roastHint") },
            { value: "max", label: t("max"), hint: t("maxHint") },
          ]}
        />
      ) : null}
      {savage ? null : <p className="text-sm text-muted">{t("locked")}</p>}
      <PreviewCard preview={preview} onAnother={() => setRound((n) => n + 1)} />
    </>
  );
}

function PreviewCard({ preview, onAnother }: { preview: Preview; onAnother: () => void }) {
  const t = useTranslations("onboarding.coach");
  return (
    <section aria-labelledby="coach-preview" className="rounded-card border border-border bg-surface-2 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="coach-preview" className="flex items-center gap-2 text-label font-semibold uppercase tracking-[0.08em] text-muted">
          <MessageSquareQuote aria-hidden className="size-4" />
          {t("preview")}
        </h2>
        {preview.state === "ok" && preview.line.savage ? (
          <Badge tone="bad">
            <Flame aria-hidden className="size-3.5" />
            {t("savageBadge")}
          </Badge>
        ) : null}
      </div>
      <div aria-live="polite" className="min-h-14">
        {preview.state === "loading" ? <Skeleton className="h-6 w-4/5" /> : null}
        {preview.state === "ok" ? <p className="text-lg font-semibold leading-snug">“{preview.line.line}”</p> : null}
        {preview.state === "failed" ? <p className="text-sm text-muted">{t("previewError")}</p> : null}
      </div>
      <Button type="button" variant="ghost" size="sm" className="mt-2 -ml-2" onClick={onAnother}>
        <RefreshCw aria-hidden />
        {t("another")}
      </Button>
    </section>
  );
}

/** A fresh sample line whenever the voice, the language or `round` changes. */
function useCoachPreview(voice: Voice, lang: string, round: number): Preview {
  const [preview, setPreview] = useState<Preview>({ state: "loading" });
  const { tone, intensity, profanity } = voice;
  useEffect(() => {
    const controller = new AbortController();
    void bffGet<CoachPreview>("/v1/me/coach-preview", { tone, intensity, profanity, lang }, { signal: controller.signal }).then(
      (result) => {
        if (controller.signal.aborted) return;
        setPreview(result.ok && result.data ? { state: "ok", line: result.data } : { state: "failed" });
      },
    );
    return () => controller.abort();
  }, [tone, intensity, profanity, lang, round]);
  return preview;
}
