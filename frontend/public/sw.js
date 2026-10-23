// Mode solo hors ligne : réseau d'abord (toujours la dernière version quand on est
// connecté), sinon la copie gardée en cache.
const CACHE = "arc-replay-solo-v1";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

// Fichiers déjà chargés avant l'installation du service worker
self.addEventListener("message", (e) => {
  if (e.data?.type !== "precharger") return;
  e.waitUntil(caches.open(CACHE).then((c) => Promise.all(e.data.fichiers.map((u) => c.add(u).catch(() => {})))));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== location.origin) return;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    try {
      const rep = await fetch(req);
      if (rep.ok) cache.put(req, rep.clone());
      return rep;
    } catch (err) {
      const copie = await cache.match(req, { ignoreSearch: true })
        || (req.mode === "navigate" && (await cache.match(new URL("./", self.registration.scope).href)));
      if (copie) return copie;
      throw err;
    }
  })());
});
