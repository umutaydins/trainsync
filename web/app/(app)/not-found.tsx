import Link from "next/link";

import { EmptyState } from "@/components/ui";

export default function NotFound() {
  return (
    <EmptyState title="Not found">
      <Link href="/activities" className="text-accent hover:underline">Back to activities</Link>
    </EmptyState>
  );
}
