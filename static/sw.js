/**
 * CHAPTR Service Worker
 *
 * Uses Workbox for caching strategies:
 * - Cache-First: Static assets (HTML, CSS, JS, images)
 * - Network-First: API calls (with offline fallback)
 *
 * Service Worker is independent of storage mode:
 * - Mode 1 (Full): Benefits from asset caching + offline capability
 * - Mode 2/3: Benefits from asset caching only
 */

// Import Workbox from CDN
importScripts('https://storage.googleapis.com/workbox-cdn/releases/7.0.0/workbox-sw.js');

const { registerRoute } = workbox.routing;
const { CacheFirst, NetworkFirst } = workbox.strategies;
const { ExpirationPlugin } = workbox.expiration;
const { CacheableResponsePlugin } = workbox.cacheableResponse;

// ==================== APP SHELL PRECACHING ====================

/**
 * Precache critical app shell files
 *
 * These files are cached on service worker installation
 * and updated when the service worker updates.
 */
workbox.precaching.precacheAndRoute([
    { url: '/static/index.html', revision: '1' },
    { url: '/static/css/style.css', revision: '1' },
    { url: '/static/js/app.js', revision: '1' },
    { url: '/static/js/db.js', revision: '1' },
    { url: '/static/js/storage-adapter.js', revision: '1' },
    { url: '/static/js/utils.js', revision: '1' },
    { url: '/static/js/projection.js', revision: '1' }
]);

// ==================== STATIC ASSETS: CACHE-FIRST ====================

/**
 * Cache-First strategy for static assets
 *
 * Priority: Cache → Network
 * - Faster loads on repeat visits
 * - 7-day cache expiration
 * - Max 60 entries to prevent unbounded growth
 */
registerRoute(
    ({ request }) => ['style', 'script', 'image', 'font'].includes(request.destination),
    new CacheFirst({
        cacheName: 'static-assets-v1',
        plugins: [
            new CacheableResponsePlugin({
                statuses: [0, 200] // Cache successful responses
            }),
            new ExpirationPlugin({
                maxEntries: 60,
                maxAgeSeconds: 7 * 24 * 60 * 60 // 7 days
            })
        ]
    })
);

// ==================== API CALLS: NETWORK-FIRST ====================

/**
 * Network-First strategy for API calls
 *
 * Priority: Network → Cache
 * - Always try network first for fresh data
 * - 5-second timeout before falling back to cache
 * - Cache as offline fallback
 */
registerRoute(
    ({ url }) => url.pathname.startsWith('/api/'),
    new NetworkFirst({
        cacheName: 'api-cache-v1',
        networkTimeoutSeconds: 5,
        plugins: [
            new CacheableResponsePlugin({
                statuses: [0, 200]
            }),
            new ExpirationPlugin({
                maxEntries: 50,
                maxAgeSeconds: 24 * 60 * 60 // 1 day
            })
        ]
    })
);

// ==================== BACKGROUND SYNC ====================

/**
 * Background sync listener
 *
 * Triggered when:
 * - App calls registration.sync.register('chaptr-sync')
 * - Browser detects connectivity restored
 *
 * Notifies app to process sync queue.
 */
self.addEventListener('sync', (event) => {
    if (event.tag === 'chaptr-sync') {
        event.waitUntil(notifyClientsToSync());
    }
});

/**
 * Notify all clients to trigger sync
 */
async function notifyClientsToSync() {
    const clients = await self.clients.matchAll({ type: 'window' });

    clients.forEach(client => {
        client.postMessage({
            type: 'BACKGROUND_SYNC',
            timestamp: new Date().toISOString()
        });
    });
}

// ==================== SERVICE WORKER LIFECYCLE ====================

/**
 * Install event - precache app shell
 */
self.addEventListener('install', (event) => {
    console.log('[SW] Service worker installing...');
    self.skipWaiting(); // Activate immediately
});

/**
 * Activate event - clean old caches
 */
self.addEventListener('activate', (event) => {
    console.log('[SW] Service worker activating...');

    const cacheWhitelist = ['static-assets-v1', 'api-cache-v1'];

    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (!cacheWhitelist.includes(cacheName)) {
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            return self.clients.claim(); // Take control immediately
        })
    );
});

// ==================== FETCH EVENT ====================

/**
 * Fetch event - handled by Workbox strategies above
 *
 * Routes:
 * - Static assets (CSS, JS, images) → Cache-First
 * - API calls (/api/*) → Network-First
 * - Everything else → Network-only
 */
self.addEventListener('fetch', (event) => {
    // Workbox handles routing via registerRoute() calls above
    // This listener is just for logging/debugging
    if (event.request.url.includes('/api/')) {
        console.log('[SW] API request:', event.request.url);
    }
});
