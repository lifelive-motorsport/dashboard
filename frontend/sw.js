// Cache de l'enveloppe applicative uniquement ; les données (/api) ne sont jamais mises en cache.
const C = 'shell-v1', SHELL = ['/', 'style.css', 'app.js', 'manifest.json', 'icon.svg'];
self.addEventListener('install', e => e.waitUntil(caches.open(C).then(c => c.addAll(SHELL))));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
