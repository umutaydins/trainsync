import type { ReactNode } from "react";

/**
 * A short rise between pages, in CSS so the first paint never waits for JavaScript (an opacity
 * fade from 0 kept the largest paint hidden until hydration). Reduced motion turns it off
 * (globals.css).
 */
export default function PageTransition({ children }: { children: ReactNode }) {
  return <div className="animate-page-in">{children}</div>;
}
