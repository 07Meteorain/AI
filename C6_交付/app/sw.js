/* PromptGate · service worker
 * 目标只有一个：二次打开不再依赖网络。
 * 策略是 stale-while-revalidate —— 先给缓存（快），后台更新下一版。
 * 注意：只缓存同源的 app 资源，不做任何跨域请求。
 */
'use strict';

var CACHE = 'promptgate-v1.0.0';
var ASSETS = [
  './',
  'index.html',
  'styles.css',
  'manifest.webmanifest',
  'assets/icon.svg',
  'js/core/util.js',
  'js/core/parser.js',
  'js/core/tokenizer.js',
  'js/core/diff.js',
  'js/core/rules.js',
  'js/core/gate.js',
  'js/core/exporter.js',
  'js/core/storage.js',
  'js/core/models.js',
  'js/core/samples.js',
  'js/core/report.js',
  'js/ui.js',
  'js/app.js'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(ASSETS).catch(function () { /* 缺资源不应让安装失败 */ });
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return k === CACHE ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    caches.match(req).then(function (cached) {
      var network = fetch(req).then(function (res) {
        if (res && res.status === 200 && res.type === 'basic') {
          var copy = res.clone();
          caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
        }
        return res;
      }).catch(function () { return cached; });
      return cached || network;
    })
  );
});
