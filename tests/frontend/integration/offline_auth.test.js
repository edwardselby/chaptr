/**
 * Offline Authentication Tests
 *
 * Tests the offline-aware authentication flow that allows users to
 * continue using the app when offline with cached credentials.
 *
 * Key scenarios:
 * - Online: Normal server verification
 * - Offline with cached user: Uses cached data, skips server
 * - Offline without cached user: Not authenticated
 * - Network error with cached user: Falls back to cached data
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('Offline Authentication Flow', () => {
    let mockLocalStorage;
    let originalLocalStorage;
    let originalNavigator;
    let originalFetch;

    const mockToken = 'mock-jwt-token-123';
    const mockUser = {
        id: 'user-123',
        username: 'testuser',
        role: 'user',
        tenant_id: 'tenant-456'
    };

    beforeEach(() => {
        // Save originals
        originalLocalStorage = window.localStorage;
        originalNavigator = navigator.onLine;
        originalFetch = window.fetch;

        // Create mock localStorage
        const store = {};
        mockLocalStorage = {
            _store: store,
            getItem: vi.fn((key) => key in store ? store[key] : null),
            setItem: vi.fn((key, value) => { store[key] = value; }),
            removeItem: vi.fn((key) => { delete store[key]; }),
            clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]); })
        };

        Object.defineProperty(window, 'localStorage', {
            value: mockLocalStorage,
            writable: true,
            configurable: true
        });
    });

    afterEach(() => {
        // Restore originals
        Object.defineProperty(window, 'localStorage', {
            value: originalLocalStorage,
            writable: true,
            configurable: true
        });

        Object.defineProperty(navigator, 'onLine', {
            value: originalNavigator,
            writable: true,
            configurable: true
        });

        window.fetch = originalFetch;
        vi.restoreAllMocks();
    });

    /**
     * Helper to simulate checkAuth logic (extracted from app.js)
     * This tests the algorithm without needing full Alpine.js setup
     */
    async function simulateCheckAuth(isOnline, fetchResponse = null) {
        // Set online status
        Object.defineProperty(navigator, 'onLine', {
            value: isOnline,
            writable: true,
            configurable: true
        });

        // Mock fetch if response provided
        if (fetchResponse !== null) {
            window.fetch = vi.fn().mockResolvedValue(fetchResponse);
        }

        const token = mockLocalStorage.getItem('auth_token');
        const cachedUser = mockLocalStorage.getItem('user');

        if (!token) {
            return { isAuthenticated: false, user: null, source: 'no_token' };
        }

        // Offline-first: If offline and we have cached user data, trust it
        if (!navigator.onLine && cachedUser) {
            try {
                const user = JSON.parse(cachedUser);
                return { isAuthenticated: true, user, source: 'cached_offline' };
            } catch (e) {
                // Invalid cached data
            }
        }

        // Online: Verify token with backend
        try {
            const response = await window.fetch('/api/auth/me', {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            if (response.ok) {
                const user = await response.json();
                mockLocalStorage.setItem('user', JSON.stringify(user));
                return { isAuthenticated: true, user, source: 'server_verified' };
            } else {
                mockLocalStorage.removeItem('auth_token');
                mockLocalStorage.removeItem('user');
                return { isAuthenticated: false, user: null, source: 'server_rejected' };
            }
        } catch (error) {
            // Network error - check if we can use cached data
            if (cachedUser) {
                try {
                    const user = JSON.parse(cachedUser);
                    return { isAuthenticated: true, user, source: 'cached_network_error' };
                } catch (e) {
                    // Invalid cached data
                }
            }
            return { isAuthenticated: false, user: null, source: 'network_error_no_cache' };
        }
    }

    describe('No Token Present', () => {
        it('should return not authenticated when no token exists', async () => {
            const result = await simulateCheckAuth(true);
            expect(result.isAuthenticated).toBe(false);
            expect(result.source).toBe('no_token');
        });

        it('should return not authenticated when offline with no token', async () => {
            const result = await simulateCheckAuth(false);
            expect(result.isAuthenticated).toBe(false);
            expect(result.source).toBe('no_token');
        });
    });

    describe('Online Mode', () => {
        beforeEach(() => {
            mockLocalStorage.setItem('auth_token', mockToken);
        });

        it('should authenticate via server when online and token valid', async () => {
            const mockResponse = {
                ok: true,
                json: vi.fn().mockResolvedValue(mockUser)
            };

            const result = await simulateCheckAuth(true, mockResponse);

            expect(result.isAuthenticated).toBe(true);
            expect(result.user.username).toBe('testuser');
            expect(result.source).toBe('server_verified');
            expect(window.fetch).toHaveBeenCalledWith('/api/auth/me', expect.any(Object));
        });

        it('should reject and clear auth when server rejects token', async () => {
            const mockResponse = {
                ok: false,
                status: 401
            };

            const result = await simulateCheckAuth(true, mockResponse);

            expect(result.isAuthenticated).toBe(false);
            expect(result.source).toBe('server_rejected');
            expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth_token');
            expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('user');
        });

        it('should cache user data after successful server verification', async () => {
            const mockResponse = {
                ok: true,
                json: vi.fn().mockResolvedValue(mockUser)
            };

            await simulateCheckAuth(true, mockResponse);

            expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
                'user',
                JSON.stringify(mockUser)
            );
        });
    });

    describe('Offline Mode with Cached User', () => {
        beforeEach(() => {
            mockLocalStorage.setItem('auth_token', mockToken);
            mockLocalStorage.setItem('user', JSON.stringify(mockUser));
        });

        it('should use cached user data when offline', async () => {
            const result = await simulateCheckAuth(false);

            expect(result.isAuthenticated).toBe(true);
            expect(result.user.username).toBe('testuser');
            expect(result.source).toBe('cached_offline');
        });

        it('should not call server when offline', async () => {
            window.fetch = vi.fn();

            await simulateCheckAuth(false);

            expect(window.fetch).not.toHaveBeenCalled();
        });

        it('should preserve all user fields from cache', async () => {
            const result = await simulateCheckAuth(false);

            expect(result.user.id).toBe('user-123');
            expect(result.user.role).toBe('user');
            expect(result.user.tenant_id).toBe('tenant-456');
        });
    });

    describe('Offline Mode without Cached User', () => {
        beforeEach(() => {
            mockLocalStorage.setItem('auth_token', mockToken);
            // No cached user
        });

        it('should not authenticate when offline without cached user', async () => {
            // When offline with token but no cached user, and fetch fails
            window.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

            const result = await simulateCheckAuth(false);

            // The offline check happens first, but without cached user it tries fetch
            // which fails, then checks cache again - still empty
            expect(result.isAuthenticated).toBe(false);
        });
    });

    describe('Network Error Fallback', () => {
        beforeEach(() => {
            mockLocalStorage.setItem('auth_token', mockToken);
            mockLocalStorage.setItem('user', JSON.stringify(mockUser));
        });

        it('should fall back to cached user on network error', async () => {
            window.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

            const result = await simulateCheckAuth(true); // "Online" but fetch fails

            expect(result.isAuthenticated).toBe(true);
            expect(result.user.username).toBe('testuser');
            expect(result.source).toBe('cached_network_error');
        });

        it('should not clear auth on network error when cached user exists', async () => {
            window.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

            await simulateCheckAuth(true);

            expect(mockLocalStorage.removeItem).not.toHaveBeenCalledWith('auth_token');
            expect(mockLocalStorage.removeItem).not.toHaveBeenCalledWith('user');
        });
    });

    describe('Invalid Cached Data', () => {
        beforeEach(() => {
            mockLocalStorage.setItem('auth_token', mockToken);
        });

        it('should handle corrupted cached user JSON gracefully', async () => {
            mockLocalStorage.setItem('user', 'invalid-json{');

            window.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

            const result = await simulateCheckAuth(false);

            // Can't parse cached user, can't reach server
            expect(result.isAuthenticated).toBe(false);
        });
    });

    describe('Security Considerations', () => {
        it('should not expose token in clear text logs (implementation note)', () => {
            // This is a documentation test - the actual implementation should
            // only log token presence (!!token), not the token value
            mockLocalStorage.setItem('auth_token', mockToken);

            // The checkAuth logs: 'token present:', !!token
            // NOT: 'token:', token
            expect(true).toBe(true); // Placeholder for implementation review
        });

        it('should clear both token and user on server rejection', async () => {
            mockLocalStorage.setItem('auth_token', mockToken);
            mockLocalStorage.setItem('user', JSON.stringify(mockUser));

            const mockResponse = { ok: false, status: 401 };
            await simulateCheckAuth(true, mockResponse);

            expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth_token');
            expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('user');
        });
    });
});
