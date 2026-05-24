self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (error) {
    payload = {
      title: 'Správa vozidel',
      body: event.data ? event.data.text() : 'Nová notifikace',
    };
  }

  const title = payload.title || 'Správa vozidel';
  const options = {
    body: payload.body || 'Máte nové upozornění.',
    icon: payload.icon || '/web/assets/toozservis-logo-icon.png',
    badge: payload.badge || '/web/assets/toozservis-logo-icon.png',
    tag: payload.tag || 'sprava-vozidel-notification',
    data: {
      url: payload.url || '/web/index.html',
      timestamp: payload.timestamp || Date.now(),
    },
    renotify: false,
    requireInteraction: false,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const targetUrl = (event.notification && event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/web/index.html';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if (client.url && client.url.includes('/web/')) {
          client.focus();
          // Kanonický typ; stránka akceptuje i legacy TOOZHUB_NOTIFICATION_CLICK (starý SW) – viz index.html
          client.postMessage({ type: 'SPRAVA_VOZIDEL_NOTIFICATION_CLICK', url: targetUrl });
          return client.navigate(targetUrl);
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
