"use client";

import { motion, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

import { DURATION, EASE_OUT } from "@/lib/motion";

/** A short fade-and-rise between pages (none with reduced motion). */
export default function PageTransition({ children }: { children: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: DURATION.base, ease: EASE_OUT }}
    >
      {children}
    </motion.div>
  );
}
