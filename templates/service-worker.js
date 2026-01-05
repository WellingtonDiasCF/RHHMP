{% load static %}
// MUDANÇA AQUI: Alterei para v2 para forçar a atualização do cache nos celulares
const CACHE_NAME = 'rh-dividata-v2';
const OFFLINE_URL = '/offline/';
const LOGO_URL = "{% static 'images/icon.svg' %}";

self.addEventListener('install', (event) => {
  self.skipWaiting(); // Força o novo service worker a assumir imediatamente
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll([
        OFFLINE_URL,
        LOGO_URL,
      ]);
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          // Apaga o cache antigo (v1) se o nome for diferente do atual (v2)
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim(); // Controla a página imediatamente
});

self.addEventListener('fetch', (event) => {
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => {
        return caches.match(OFFLINE_URL);
      })
    );
  } else {
    event.respondWith(
      caches.match(event.request).then((response) => {
        return response || fetch(event.request);
      })
    );
  }
});