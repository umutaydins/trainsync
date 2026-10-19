/** Runs once when the server starts (Next.js instrumentation hook). */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const { warnDevSecrets } = await import("@/lib/dev-defaults");
  warnDevSecrets(process.env);
}
