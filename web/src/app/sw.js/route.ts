/**
 * The service worker (ADR 0039): caches the app shell (the offline page, icons) per build and shows
 * the offline page when a navigation fails. API calls and pages with data are never cached.
 */
const VERSION = process.env.NEXT_PUBLIC_BUILD_ID ?? "dev";
const SHELL = ["/offline", "/icon.svg", "/icons/icon-192.png", "/manifest.webmanifest"];

const SCRIPT = `
const CACHE = "trainsync-shell-${VERSION}";
const SHELL = ${JSON.stringify(SHELL)};
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});
self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline")));
    return;
  }
  const url = new URL(request.url);
  if (url.origin === self.location.origin && SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request)));
  }
});
`;

export function GET(): Response {
  return new Response(SCRIPT, {
    headers: {
      "content-type": "text/javascript; charset=utf-8",
      "cache-control": "no-cache",
      "service-worker-allowed": "/",
    },
  });
}
