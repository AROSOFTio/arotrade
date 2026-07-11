/* Minimal service worker: enables PWA installability. Network-first, no caching
   of API responses so trading data is never stale. */
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))
self.addEventListener('fetch', (event) => {
  // Pass-through; presence of a fetch handler is required for install prompts.
  event.respondWith(fetch(event.request).catch(() => new Response('Offline', { status: 503 })))
})
