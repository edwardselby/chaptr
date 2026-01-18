/**
 * Integration tests for API authentication
 *
 * Tests the apiRequest function from static/js/utils.js:175-196
 * - Bearer token injection into Authorization header
 * - 401 Unauthorized response handling (clearAuth + throw)
 * - Successful response passthrough
 * - Non-401 error response passthrough
 *
 * Note: window.location.reload cannot be mocked in browser environment.
 * We verify 401 handling by checking clearAuth is called and error is thrown.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiRequest } from '../../../static/js/utils.js';

describe('API Authentication - apiRequest', () => {
  let store;
  let fetchSpy;
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

    // Replace localStorage
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      writable: true,
      configurable: true
    });

    // Mock fetch using spyOn (consistent with other tests)
    fetchSpy = vi.spyOn(window, 'fetch');
  });

  afterEach(() => {
    // Restore original localStorage
    Object.defineProperty(window, 'localStorage', {
      value: originalLocalStorage,
      writable: true,
      configurable: true
    });

    // Restore fetch
    vi.restoreAllMocks();
  });

  describe('Bearer Token Injection', () => {
    it('adds Authorization header when token exists', async () => {
      store['auth_token'] = 'my-jwt-token';

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200
      });

      await apiRequest('/api/test');

      expect(fetchSpy).toHaveBeenCalledWith('/api/test', {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer my-jwt-token'
        }
      });
    });

    it('does not add Authorization header when no token', async () => {
      // No token in store

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200
      });

      await apiRequest('/api/test');

      expect(fetchSpy).toHaveBeenCalledWith('/api/test', {
        headers: {
          'Content-Type': 'application/json'
        }
      });
    });

    it('preserves other headers from options', async () => {
      store['auth_token'] = 'token';

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200
      });

      await apiRequest('/api/test', {
        headers: {
          'X-Custom-Header': 'custom-value'
        }
      });

      expect(fetchSpy).toHaveBeenCalledWith('/api/test', {
        headers: {
          'Content-Type': 'application/json',
          'X-Custom-Header': 'custom-value',
          'Authorization': 'Bearer token'
        }
      });
    });

    it('allows Content-Type to be overridden', async () => {
      store['auth_token'] = 'token';

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200
      });

      await apiRequest('/api/test', {
        headers: {
          'Content-Type': 'text/plain'
        }
      });

      // Custom Content-Type should override default
      expect(fetchSpy).toHaveBeenCalledWith('/api/test', {
        headers: {
          'Content-Type': 'text/plain',
          'Authorization': 'Bearer token'
        }
      });
    });

    it('passes through method and body options', async () => {
      store['auth_token'] = 'token';

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 201
      });

      await apiRequest('/api/users', {
        method: 'POST',
        body: JSON.stringify({ username: 'test' })
      });

      expect(fetchSpy).toHaveBeenCalledWith('/api/users', {
        method: 'POST',
        body: JSON.stringify({ username: 'test' }),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer token'
        }
      });
    });
  });

  describe('401 Response Handling', () => {
    it('clears auth data on 401 response', async () => {
      store['auth_token'] = 'expired-token';
      store['user'] = JSON.stringify({ id: '123' });

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 401
      });

      try {
        await apiRequest('/api/test');
      } catch (e) {
        // Expected to throw
      }

      // Verify clearAuth was called (removeItem for both keys)
      expect(localStorage.removeItem).toHaveBeenCalledWith('auth_token');
      expect(localStorage.removeItem).toHaveBeenCalledWith('user');
    });

    it('throws Unauthorized error on 401', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 401
      });

      await expect(apiRequest('/api/test')).rejects.toThrow('Unauthorized');
    });

    it('clears auth before throwing on 401', async () => {
      store['auth_token'] = 'token';
      store['user'] = '{"id":"123"}';

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 401
      });

      // Capture when clearAuth was called vs when error was thrown
      let clearAuthCalled = false;
      const originalRemoveItem = localStorage.removeItem;
      localStorage.removeItem = vi.fn((key) => {
        if (key === 'auth_token') {
          clearAuthCalled = true;
        }
        originalRemoveItem(key);
      });

      let errorThrown = false;
      try {
        await apiRequest('/api/test');
      } catch (e) {
        errorThrown = true;
        // At point of error, clearAuth should already have been called
        expect(clearAuthCalled).toBe(true);
      }

      expect(errorThrown).toBe(true);
    });
  });

  describe('Successful Responses', () => {
    it('returns response object for 200 OK', async () => {
      const mockResponse = {
        ok: true,
        status: 200,
        json: () => Promise.resolve({ data: 'test' })
      };

      fetchSpy.mockResolvedValueOnce(mockResponse);

      const response = await apiRequest('/api/test');

      expect(response).toBe(mockResponse);
      expect(response.ok).toBe(true);
      expect(response.status).toBe(200);
    });

    it('returns response object for 201 Created', async () => {
      const mockResponse = {
        ok: true,
        status: 201,
        json: () => Promise.resolve({ id: 'new-id' })
      };

      fetchSpy.mockResolvedValueOnce(mockResponse);

      const response = await apiRequest('/api/users', { method: 'POST' });

      expect(response).toBe(mockResponse);
      expect(response.status).toBe(201);
    });

    it('returns response object for 204 No Content', async () => {
      const mockResponse = {
        ok: true,
        status: 204
      };

      fetchSpy.mockResolvedValueOnce(mockResponse);

      const response = await apiRequest('/api/users/123', { method: 'DELETE' });

      expect(response.status).toBe(204);
    });

    it('allows caller to parse JSON response', async () => {
      const mockData = { users: [{ id: '1', name: 'Test' }] };

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(mockData)
      });

      const response = await apiRequest('/api/users');
      const data = await response.json();

      expect(data).toEqual(mockData);
    });
  });

  describe('Error Responses (non-401)', () => {
    it('returns response for 400 Bad Request (does not clear auth)', async () => {
      store['auth_token'] = 'valid-token';

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: 'Invalid input' })
      });

      const response = await apiRequest('/api/test');

      expect(response.status).toBe(400);
      expect(localStorage.removeItem).not.toHaveBeenCalled();
    });

    it('returns response for 403 Forbidden (does not clear auth)', async () => {
      store['auth_token'] = 'valid-token';

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: 'Permission denied' })
      });

      const response = await apiRequest('/api/admin/users');

      expect(response.status).toBe(403);
      expect(localStorage.removeItem).not.toHaveBeenCalled();
    });

    it('returns response for 404 Not Found (does not clear auth)', async () => {
      store['auth_token'] = 'valid-token';

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Not found' })
      });

      const response = await apiRequest('/api/users/nonexistent');

      expect(response.status).toBe(404);
      expect(localStorage.removeItem).not.toHaveBeenCalled();
    });

    it('returns response for 500 Internal Server Error (does not clear auth)', async () => {
      store['auth_token'] = 'valid-token';

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Server error' })
      });

      const response = await apiRequest('/api/test');

      expect(response.status).toBe(500);
      expect(localStorage.removeItem).not.toHaveBeenCalled();
    });

    it('allows caller to handle error response JSON', async () => {
      const errorDetail = { detail: 'Username already exists' };

      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve(errorDetail)
      });

      const response = await apiRequest('/api/users', { method: 'POST' });
      const error = await response.json();

      expect(error.detail).toBe('Username already exists');
    });
  });

  describe('Network Errors', () => {
    it('propagates fetch network errors', async () => {
      fetchSpy.mockRejectedValueOnce(new Error('Network error'));

      await expect(apiRequest('/api/test')).rejects.toThrow('Network error');

      // Should not call clearAuth for network errors
      expect(localStorage.removeItem).not.toHaveBeenCalled();
    });

    it('propagates fetch timeout errors', async () => {
      fetchSpy.mockRejectedValueOnce(new Error('Request timed out'));

      await expect(apiRequest('/api/test')).rejects.toThrow('Request timed out');
    });
  });

  describe('Request URL Handling', () => {
    it('handles absolute URLs', async () => {
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200 });

      await apiRequest('/api/users');

      expect(fetchSpy).toHaveBeenCalledWith('/api/users', expect.any(Object));
    });

    it('handles URLs with query parameters', async () => {
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200 });

      await apiRequest('/api/users?role=admin&limit=10');

      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/users?role=admin&limit=10',
        expect.any(Object)
      );
    });

    it('handles URLs with path parameters', async () => {
      fetchSpy.mockResolvedValueOnce({ ok: true, status: 200 });

      await apiRequest('/api/users/123-456-789/profile');

      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/users/123-456-789/profile',
        expect.any(Object)
      );
    });
  });
});
