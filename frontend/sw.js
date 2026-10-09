// Cache de l'enveloppe applicative uniquement ; les données (/api) ne sont jamais mises en cache.
const C = 'shell-v202', SHELL = ['/', 'style.css', 'app.js', 'adjust.js', 'stock.js', 'analytics.js', 'tags.js', 'expenses.js', 'netmargin.js', 'stockvar.js', 'margins.js', 'tn11.js', 'users.js', 'bu.js', 'bufilter.js', 'home.js', 'changelog.js', 'projections.js', 'tablesort.js', 'staffcalc.js', 'staffdata.js', 'manifest.json', 'icon-192.png', 'favicon.png', 'favicon.svg', 'brand/logbook-icon.svg', 'brand/LOGO_LIFELIVE_White.svg', 'brand/LOGO_LIFELIVE_Black.svg'];
self.addEventListener('install', e => e.waitUntil(caches.open(C).then(c => c.addAll(SHELL))));
self.addEventListener('fetch', e => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin || u.pathname.startsWith('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
