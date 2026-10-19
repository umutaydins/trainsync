/** The trainsync mark: a rising line on the accent square. */
export function Logo({ className = "size-8" }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 32 32" className={className}>
      <rect width="32" height="32" rx="9" className="fill-accent" />
      <path
        d="M7 21l6-8 5 5 7-9"
        fill="none"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="stroke-accent-contrast"
      />
    </svg>
  );
}
