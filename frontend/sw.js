// Cache de l'enveloppe applicative uniquement ; les données (/api) ne sont jamais mises en cache.
const C = 'shell-v80', SHELL = ['/', 'style.css', 'app.js', 'adjust.js', 'stock.js', 'analytics.js', 'tags.js', 'staffcalc.js', 'staffdata.js', 'manifest.json', 'icon-192.png', 'favicon.png', 'logo-light.png', 'logo-dark.png'];
self.addEventListener('install', e => e.waitUntil(caches.open(C).then(c => c.addAll(SHELL))));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
