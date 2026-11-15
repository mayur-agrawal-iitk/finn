// Offline-first shell, fresh-first data. Lets the Brief open instantly on a phone, even on a flaky network.
const SHELL = "finn-shell-v1";
const DATA = "finn-data-v1";
const ASSETS = ["./", "index.html", "styles.css", "config.js", "icon.svg", "manifest.webmanifest",
  "js/app.js", "js/lib.js", "js/network.js", "js/rules.js", "js/cards.js",
  "js/views/brief.js", "js/views/event.js", "js/views/research.js", "js/views/network.js", "js/views/watch.js"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.includes("/data/")) {
    e.respondWith(fetch(e.request).then((r) => {
      const copy = r.clone();
      caches.open(DATA).then((c) => c.put(e.request, copy));
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request)));
});
