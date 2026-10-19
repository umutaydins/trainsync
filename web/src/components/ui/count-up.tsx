"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";

import { COUNT_UP_S, EASE_OUT } from "@/lib/motion";

/**
 * A number that counts up to `value` (from its previous value) in the user's locale. The final
 * text is rendered on the server too, so screen readers and no-JS readers get the real number.
 */
export function CountUp({
  value,
  locale,
  options,
}: {
  value: number;
  locale: string;
  options?: Intl.NumberFormatOptions;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef(0);
  const reduce = useReducedMotion();
  const format = new Intl.NumberFormat(locale, options);
  const text = format.format(value);

  useEffect(() => {
    const node = ref.current;
    if (!node || reduce) return;
    const controls = animate(previous.current, value, {
      duration: COUNT_UP_S,
      ease: EASE_OUT,
      onUpdate: (latest) => {
        node.textContent = format.format(latest);
      },
    });
    previous.current = value;
    return () => controls.stop();
    // `format` is rebuilt every render from `locale`/`options`; they are the real inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reduce, locale]);

  return (
    <span ref={ref} data-numeric>
      {text}
    </span>
  );
}
