/**
 * A short device name from a session's user agent ("Safari · iPhone"), or null when it says nothing
 * useful. Product names only, so nothing to translate. Order matters: Edge and Chrome both say
 * "Safari", iPads and iPhones both say "Mac OS X".
 */
const BROWSERS: readonly [RegExp, string][] = [
  [/Edg(?:e|A|iOS)?\//, "Edge"],
  [/OPR\/|Opera/, "Opera"],
  [/Firefox\/|FxiOS\//, "Firefox"],
  [/SamsungBrowser\//, "Samsung Internet"],
  [/Chrome\/|CriOS\//, "Chrome"],
  [/Safari\//, "Safari"],
];

const SYSTEMS: readonly [RegExp, string][] = [
  [/iPhone/, "iPhone"],
  [/iPad/, "iPad"],
  [/Android/, "Android"],
  [/Windows/, "Windows"],
  [/Mac OS X|Macintosh/, "macOS"],
  [/CrOS/, "ChromeOS"],
  [/Linux/, "Linux"],
];

function first(table: readonly [RegExp, string][], agent: string): string | null {
  return table.find(([pattern]) => pattern.test(agent))?.[1] ?? null;
}

export function deviceName(userAgent: string | null | undefined): string | null {
  if (!userAgent) return null;
  const parts = [first(BROWSERS, userAgent), first(SYSTEMS, userAgent)].filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(" · ") : null;
}
