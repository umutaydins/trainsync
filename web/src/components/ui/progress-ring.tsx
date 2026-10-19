"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import { DURATION } from "@/lib/motion";

const VIEWBOX = 120;
const STROKE = 10;
const RADIUS = (VIEWBOX - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** A ring that fills from 0 to `value` (0..1); the rest timer and goal progress use it. */
export function ProgressRing({
  value,
  size = 240,
  label,
  children,
}: {
  value: number;
  size?: number;
  label: string;
  children?: ReactNode;
}) {
  const reduce = useReducedMotion();
  const clamped = Math.min(1, Math.max(0, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped * 100)}
      className="relative grid place-items-center"
      style={{ width: size, height: size }}
    >
      <svg viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`} className="absolute inset-0 -rotate-90" aria-hidden>
        <circle
          cx={VIEWBOX / 2}
          cy={VIEWBOX / 2}
          r={RADIUS}
          fill="none"
          strokeWidth={STROKE}
          className="stroke-surface-3"
        />
        <motion.circle
          cx={VIEWBOX / 2}
          cy={VIEWBOX / 2}
          r={RADIUS}
          fill="none"
          strokeWidth={STROKE}
          strokeLinecap="round"
          className="stroke-accent"
          strokeDasharray={CIRCUMFERENCE}
          animate={{ strokeDashoffset: CIRCUMFERENCE * (1 - clamped) }}
          transition={{ duration: reduce ? 0 : DURATION.base, ease: "linear" }}
        />
      </svg>
      <div className="relative text-center">{children}</div>
    </div>
  );
}
