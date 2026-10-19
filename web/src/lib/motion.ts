/** Motion timings (ms and seconds) shared by `motion` components; tokens.css has the CSS ones. */

export const DURATION = { fast: 0.12, base: 0.22, slow: 0.42 } as const;
export const EASE_OUT = [0.16, 1, 0.3, 1] as const;
/** A number counts up from 0 to its value this fast on first render or when it changes. */
export const COUNT_UP_S = 0.6;
