"use client";

import { ErrorState, secondaryButtonClass } from "@/components/ui";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="space-y-3">
      <ErrorState title="Something went wrong" message="The page could not be rendered." />
      <button type="button" onClick={reset} className={secondaryButtonClass}>Try again</button>
    </div>
  );
}
