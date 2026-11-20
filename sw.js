const SHELL = 'shell-v1';
const FILES = ['./', './index.html', './manifest.webmanifest', './icons/icon-192.png'];
self.addEventListener('install', (e) => { e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== SHELL && k !== 'data').map((k) => caches.delete(k))))); self.clients.claim(); });
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return;
  // 데이터와 페이지는 네트워크 우선, 안 되면 마지막 저장본
  e.respondWith(fetch(e.request).then((r) => {
    const copy = r.clone();
    caches.open(url.pathname.includes('/data/') ? 'data' : SHELL).then((c) => c.put(e.request, copy));
    return r;
  }).catch(() => caches.match(e.request, { ignoreSearch: true })));
});
