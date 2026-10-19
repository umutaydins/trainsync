"use client";

import { ArrowLeft, ArrowRight, PartyPopper } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { CoachStep } from "@/features/onboarding/components/coach-step";
import { LanguageStep, TimeZoneStep } from "@/features/onboarding/components/preference-steps";
import { ProfileStep } from "@/features/onboarding/components/profile-step";
import { StepFrame } from "@/features/onboarding/components/step-frame";
import { StravaStep } from "@/features/onboarding/components/strava-step";
import { TelegramStep } from "@/features/onboarding/components/telegram-step";
import { STEPS, type Step, initialStep, isLast, nextStep, previousStep } from "@/features/onboarding/steps";
import type { OnboardingData } from "@/features/onboarding/types";
import { cn } from "@/lib/cn";
import { DURATION, EASE_OUT } from "@/lib/motion";

const SLIDE_PX = 32;

/** First-run setup, one step at a time; every step can be skipped and revisited from Me. */
export function OnboardingFlow({ data }: { data: OnboardingData }) {
  const common = useTranslations("common.actions");
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(() => initialStep(data.stravaReturn));
  const [direction, setDirection] = useState(1);
  const step = STEPS[index] ?? "done";
  const last = isLast(index);

  const go = useCallback(
    (to: number) => {
      setDirection(to >= index ? 1 : -1);
      setIndex(to);
    },
    [index],
  );
  const onNext = useCallback(() => go(nextStep(index)), [go, index]);

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={common("back")}
          disabled={index === 0}
          onClick={() => go(previousStep(index))}
        >
          <ArrowLeft aria-hidden />
        </Button>
        <Progress index={index} />
        {last ? (
          <span className="size-touch" />
        ) : (
          <Button type="button" variant="ghost" onClick={onNext}>
            {common("skip")}
          </Button>
        )}
      </div>
      <motion.div
        key={step}
        initial={reduced ? { opacity: 0 } : { opacity: 0, x: direction * SLIDE_PX }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: reduced ? DURATION.fast : DURATION.base, ease: EASE_OUT }}
      >
        <StepBody step={step} data={data} onNext={onNext} />
      </motion.div>
    </div>
  );
}

function Progress({ index }: { index: number }) {
  const t = useTranslations("onboarding");
  return (
    <div className="flex flex-1 flex-col items-center gap-2">
      <p className="text-label font-semibold uppercase tracking-[0.08em] text-muted">
        {t("progress", { current: index + 1, total: STEPS.length })}
      </p>
      <ol aria-label={t("progress", { current: index + 1, total: STEPS.length })} className="flex items-center gap-1.5">
        {STEPS.map((step, position) => (
          <li
            key={step}
            aria-current={position === index ? "step" : undefined}
            className={cn(
              "h-2 rounded-full transition-all duration-300",
              position === index ? "w-7 bg-accent" : position < index ? "w-2 bg-accent/60" : "w-2 bg-surface-3",
            )}
          >
            <span className="sr-only">{t(`steps.${step}`)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function StepBody({ step, data, onNext }: { step: Step; data: OnboardingData; onNext: () => void }) {
  switch (step) {
    case "timezone":
      return <TimeZoneStep onNext={onNext} current={data.timezone} />;
    case "language":
      return <LanguageStep onNext={onNext} current={data.settings?.lang ?? null} />;
    case "coach":
      return <CoachStep onNext={onNext} current={data.settings} />;
    case "strava":
      return <StravaStep onNext={onNext} connection={data.strava} returned={data.stravaReturn} />;
    case "telegram":
      return <TelegramStep onNext={onNext} initial={data.telegram} />;
    case "profile":
      return <ProfileStep onNext={onNext} profile={data.profile} />;
    case "done":
      return <DoneStep />;
  }
}

function DoneStep() {
  const t = useTranslations("onboarding.done");
  return (
    <StepFrame
      title={t("title")}
      body={t("body")}
      action={
        <Link href="/" className={buttonVariants({ size: "lg", block: true })}>
          {t("cta")}
          <ArrowRight aria-hidden />
        </Link>
      }
    >
      <div aria-hidden className="grid h-40 place-items-center rounded-card bg-accent text-accent-contrast">
        <PartyPopper className="size-16" strokeWidth={1.5} />
      </div>
    </StepFrame>
  );
}
