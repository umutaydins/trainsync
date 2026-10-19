import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { onboardingData } from "@/features/onboarding/api";
import { OnboardingFlow } from "@/features/onboarding/components/onboarding-flow";
import { stravaReturnFrom } from "@/features/onboarding/steps";

export const dynamic = "force-dynamic";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("onboarding");
  return { title: t("metaTitle") };
}

/** `/onboarding`: after sign-up, and from Me any time later. Strava's OAuth returns here too. */
export default async function OnboardingPage({ searchParams }: { searchParams: SearchParams }) {
  const data = await onboardingData(stravaReturnFrom(await searchParams));
  return <OnboardingFlow data={data} />;
}
