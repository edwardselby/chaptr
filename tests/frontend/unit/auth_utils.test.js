/**
 * Unit tests for authentication utility functions
 *
 * Tests JWT token management functions from static/js/utils.js:
 * - storeToken() - stores JWT in localStorage
 * - getToken() - retrieves JWT from localStorage
 * - clearAuth() - removes auth data (token + user)
 * - isAuthenticated() - checks if token exists
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  storeToken,
  getToken,
  clearAuth,
  isAuthenticated
} from '../../../static/js/utils.js';

describe('Auth Utils - Token Management', () => {
  let store;
  let originalLocalStorage;

  beforeEach(() => {
    // Create fresh store for each test
    store = {};

    // Save original localStorage
    originalLocalStorage = window.localStorage;

    // Create mock localStorage object
    const mockLocalStorage = {
      _store: store,
      getItem: vi.fn((key) => key in store ? store[key] : null),
      setItem: vi.fn((key, value) => { store[key] = value; }),
      removeItem: vi.fn((key) => { delete store[key]; }),
      clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]); })
    };

    // Replace localStorage using Object.defineProperty
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      writable: true,
      configurable: true
    });
  });

  afterEach(() => {
    // Restore original localStorage
    Object.defineProperty(window, 'localStorage', {
      value: originalLocalStorage,
      writable: true,
      configurable: true
    });

    vi.restoreAllMocks();
  });

  describe('storeToken', () => {
    it('stores token in localStorage under auth_token key', () => {
      const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test';

      storeToken(token);

      expect(localStorage.setItem).toHaveBeenCalledWith('auth_token', token);
      expect(store['auth_token']).toBe(token);
    });

    it('overwrites existing token', () => {
      store['auth_token'] = 'old-token';

      storeToken('new-token');

      expect(store['auth_token']).toBe('new-token');
    });

    it('stores empty string token', () => {
      storeToken('');

      expect(store['auth_token']).toBe('');
    });
  });

  describe('getToken', () => {
    it('returns token when present', () => {
      store['auth_token'] = 'my-jwt-token';

      const token = getToken();

      expect(token).toBe('my-jwt-token');
      expect(localStorage.getItem).toHaveBeenCalledWith('auth_token');
    });

    it('returns null when no token exists', () => {
      const token = getToken();

      expect(token).toBeNull();
    });

    it('returns empty string if stored as empty', () => {
      store['auth_token'] = '';

      const token = getToken();

      // localStorage stores as string, empty string is falsy but not null
      expect(token).toBe('');
    });
  });

  describe('clearAuth', () => {
    it('removes auth_token from localStorage', () => {
      store['auth_token'] = 'some-token';

      clearAuth();

      expect(localStorage.removeItem).toHaveBeenCalledWith('auth_token');
      expect(store['auth_token']).toBeUndefined();
    });

    it('removes user from localStorage', () => {
      store['user'] = JSON.stringify({ id: '123', username: 'test' });

      clearAuth();

      expect(localStorage.removeItem).toHaveBeenCalledWith('user');
      expect(store['user']).toBeUndefined();
    });

    it('removes both token and user', () => {
      store['auth_token'] = 'token';
      store['user'] = '{"id":"123"}';

      clearAuth();

      expect(store['auth_token']).toBeUndefined();
      expect(store['user']).toBeUndefined();
    });

    it('handles case when items do not exist', () => {
      // Should not throw when items don't exist
      expect(() => clearAuth()).not.toThrow();

      expect(localStorage.removeItem).toHaveBeenCalledWith('auth_token');
      expect(localStorage.removeItem).toHaveBeenCalledWith('user');
    });

    it('does not affect other localStorage items', () => {
      store['auth_token'] = 'token';
      store['user'] = '{"id":"123"}';
      store['other_key'] = 'should-persist';

      clearAuth();

      expect(store['other_key']).toBe('should-persist');
    });
  });

  describe('isAuthenticated', () => {
    it('returns true when token exists', () => {
      store['auth_token'] = 'valid-token';

      expect(isAuthenticated()).toBe(true);
    });

    it('returns false when no token', () => {
      expect(isAuthenticated()).toBe(false);
    });

    it('returns false after clearAuth', () => {
      store['auth_token'] = 'token';
      expect(isAuthenticated()).toBe(true);

      clearAuth();

      expect(isAuthenticated()).toBe(false);
    });

    it('returns false for empty string token (edge case)', () => {
      // Note: empty string is falsy, so !!'' returns false
      // This documents current behavior - empty token is NOT authenticated
      store['auth_token'] = '';

      expect(isAuthenticated()).toBe(false);
    });

    it('returns true for any truthy token value', () => {
      store['auth_token'] = 'a';
      expect(isAuthenticated()).toBe(true);

      store['auth_token'] = '0'; // string "0" is truthy
      expect(isAuthenticated()).toBe(true);
    });
  });

  describe('Integration: storeToken + getToken', () => {
    it('round-trips token correctly', () => {
      const originalToken = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.signature';

      storeToken(originalToken);
      const retrieved = getToken();

      expect(retrieved).toBe(originalToken);
    });
  });

  describe('Integration: Full auth lifecycle', () => {
    it('handles login -> check -> logout flow', () => {
      // Initially not authenticated
      expect(isAuthenticated()).toBe(false);

      // Login (store token)
      storeToken('jwt-token-abc');
      expect(isAuthenticated()).toBe(true);
      expect(getToken()).toBe('jwt-token-abc');

      // Logout (clear auth)
      clearAuth();
      expect(isAuthenticated()).toBe(false);
      expect(getToken()).toBeNull();
    });

    it('handles token refresh (new token while logged in)', () => {
      storeToken('old-token');
      expect(getToken()).toBe('old-token');

      // Refresh token
      storeToken('new-token');
      expect(getToken()).toBe('new-token');
      expect(isAuthenticated()).toBe(true);
    });
  });
});
