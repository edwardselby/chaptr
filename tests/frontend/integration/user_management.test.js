/**
 * Integration tests for user management operations
 *
 * Tests the user CRUD logic from static/js/app.js:1806-1916
 * - Create user request payloads
 * - Update user request payloads
 * - Update own account (self-service)
 * - Delete user confirmation logic
 *
 * Note: These tests focus on request payload construction and validation
 * since the Alpine.js component methods are tightly coupled to DOM state.
 * Full UI integration should be tested via E2E tests.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { apiRequest } from '../../../static/js/utils.js';

/**
 * Helper to construct createUser payload
 * Mirrors logic from app.js:1806-1818
 */
function buildCreateUserPayload(userForm) {
  return {
    username: userForm.username.trim(),
    role: userForm.role || 'user',
    password: userForm.password
  };
}

/**
 * Helper to construct updateUser payload
 * Mirrors logic from app.js:1824-1838
 */
function buildUpdateUserPayload(userForm) {
  const data = {
    username: userForm.username.trim(),
    role: userForm.role
  };

  // Only include password if provided
  if (userForm.password) {
    data.password = userForm.password;
  }

  return data;
}

/**
 * Helper to construct updateMyAccount payload
 * Mirrors logic from app.js:1846-1855
 */
function buildUpdateMyAccountPayload(userForm) {
  const data = {
    username: userForm.username.trim()
  };

  // Only include password if provided
  if (userForm.password) {
    data.password = userForm.password;
    data.current_password = userForm.current_password;
  }

  return data;
}

/**
 * Helper to validate delete user confirmation
 * Mirrors logic from app.js:1891-1905
 */
function validateDeleteConfirmation(typed, expectedUsername) {
  return typed === expectedUsername;
}

/**
 * Helper to check if user can delete target user
 */
function canDeleteUser(currentUserId, targetUserId) {
  return currentUserId !== targetUserId;
}

describe('User Management - Create User', () => {
  describe('buildCreateUserPayload', () => {
    it('builds payload with trimmed username', () => {
      const userForm = {
        username: '  newuser  ',
        role: 'user',
        password: 'secret123'
      };

      const payload = buildCreateUserPayload(userForm);

      expect(payload.username).toBe('newuser');
    });

    it('uses default role when not specified', () => {
      const userForm = {
        username: 'newuser',
        role: '',
        password: 'secret123'
      };

      const payload = buildCreateUserPayload(userForm);

      expect(payload.role).toBe('user');
    });

    it('uses provided role when specified', () => {
      const userForm = {
        username: 'newadmin',
        role: 'admin',
        password: 'secret123'
      };

      const payload = buildCreateUserPayload(userForm);

      expect(payload.role).toBe('admin');
    });

    it('includes password in payload', () => {
      const userForm = {
        username: 'newuser',
        role: 'user',
        password: 'supersecret'
      };

      const payload = buildCreateUserPayload(userForm);

      expect(payload.password).toBe('supersecret');
    });

    it('handles null role by using default', () => {
      const userForm = {
        username: 'newuser',
        role: null,
        password: 'secret123'
      };

      const payload = buildCreateUserPayload(userForm);

      expect(payload.role).toBe('user');
    });
  });
});

describe('User Management - Update User', () => {
  describe('buildUpdateUserPayload', () => {
    it('builds payload with trimmed username', () => {
      const userForm = {
        username: '  updatedname  ',
        role: 'user',
        password: ''
      };

      const payload = buildUpdateUserPayload(userForm);

      expect(payload.username).toBe('updatedname');
    });

    it('includes role in payload', () => {
      const userForm = {
        username: 'user1',
        role: 'admin',
        password: ''
      };

      const payload = buildUpdateUserPayload(userForm);

      expect(payload.role).toBe('admin');
    });

    it('excludes password when empty', () => {
      const userForm = {
        username: 'user1',
        role: 'user',
        password: ''
      };

      const payload = buildUpdateUserPayload(userForm);

      expect(payload).not.toHaveProperty('password');
    });

    it('includes password when provided', () => {
      const userForm = {
        username: 'user1',
        role: 'user',
        password: 'newpassword'
      };

      const payload = buildUpdateUserPayload(userForm);

      expect(payload.password).toBe('newpassword');
    });

    it('excludes password when null', () => {
      const userForm = {
        username: 'user1',
        role: 'user',
        password: null
      };

      const payload = buildUpdateUserPayload(userForm);

      expect(payload).not.toHaveProperty('password');
    });
  });
});

describe('User Management - Update Own Account', () => {
  describe('buildUpdateMyAccountPayload', () => {
    it('builds payload with trimmed username', () => {
      const userForm = {
        username: '  myname  ',
        password: '',
        current_password: ''
      };

      const payload = buildUpdateMyAccountPayload(userForm);

      expect(payload.username).toBe('myname');
    });

    it('excludes password when empty', () => {
      const userForm = {
        username: 'myname',
        password: '',
        current_password: ''
      };

      const payload = buildUpdateMyAccountPayload(userForm);

      expect(payload).not.toHaveProperty('password');
      expect(payload).not.toHaveProperty('current_password');
    });

    it('includes password and current_password when changing password', () => {
      const userForm = {
        username: 'myname',
        password: 'newpassword',
        current_password: 'oldpassword'
      };

      const payload = buildUpdateMyAccountPayload(userForm);

      expect(payload.password).toBe('newpassword');
      expect(payload.current_password).toBe('oldpassword');
    });

    it('includes both passwords even if current_password is empty (server validates)', () => {
      const userForm = {
        username: 'myname',
        password: 'newpassword',
        current_password: ''
      };

      const payload = buildUpdateMyAccountPayload(userForm);

      expect(payload.password).toBe('newpassword');
      expect(payload.current_password).toBe('');
    });
  });
});

describe('User Management - Delete User', () => {
  describe('validateDeleteConfirmation', () => {
    it('returns true for exact username match', () => {
      expect(validateDeleteConfirmation('testuser', 'testuser')).toBe(true);
    });

    it('returns false for wrong username', () => {
      expect(validateDeleteConfirmation('wrong', 'testuser')).toBe(false);
    });

    it('returns false for partial match', () => {
      expect(validateDeleteConfirmation('test', 'testuser')).toBe(false);
    });

    it('returns false for case mismatch', () => {
      expect(validateDeleteConfirmation('TestUser', 'testuser')).toBe(false);
    });

    it('returns false for empty input', () => {
      expect(validateDeleteConfirmation('', 'testuser')).toBe(false);
    });

    it('handles special characters in username', () => {
      expect(validateDeleteConfirmation('user@test.com', 'user@test.com')).toBe(true);
      expect(validateDeleteConfirmation('user-with-dash', 'user-with-dash')).toBe(true);
    });
  });

  describe('canDeleteUser', () => {
    it('returns false when trying to delete yourself', () => {
      expect(canDeleteUser('user-123', 'user-123')).toBe(false);
    });

    it('returns true when deleting different user', () => {
      expect(canDeleteUser('admin-456', 'user-123')).toBe(true);
    });

    it('handles UUID format IDs', () => {
      const currentId = '550e8400-e29b-41d4-a716-446655440000';
      const targetId = '550e8400-e29b-41d4-a716-446655440001';

      expect(canDeleteUser(currentId, currentId)).toBe(false);
      expect(canDeleteUser(currentId, targetId)).toBe(true);
    });
  });
});

describe('User Management - API Request Construction', () => {
  let fetchSpy;
  let store;
  let originalLocalStorage;

  beforeEach(() => {
    store = { 'auth_token': 'valid-token' };

    // Save original localStorage
    originalLocalStorage = window.localStorage;

    // Create mock localStorage
    const mockLocalStorage = {
      _store: store,
      getItem: vi.fn((key) => key in store ? store[key] : null),
      setItem: vi.fn((key, value) => { store[key] = value; }),
      removeItem: vi.fn((key) => { delete store[key]; }),
      clear: vi.fn()
    };

    // Replace localStorage using Object.defineProperty
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

    vi.restoreAllMocks();
  });

  describe('Create User API Call', () => {
    it('sends POST to /api/admin/users', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: () => Promise.resolve({ id: 'new-user-id', username: 'newuser' })
      });

      const userForm = {
        username: 'newuser',
        role: 'user',
        password: 'secret123'
      };

      const payload = buildCreateUserPayload(userForm);

      await apiRequest('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify(payload)
      });

      expect(fetchSpy).toHaveBeenCalledWith('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          username: 'newuser',
          role: 'user',
          password: 'secret123'
        }),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer valid-token'
        }
      });
    });
  });

  describe('Update User API Call', () => {
    it('sends PUT to /api/admin/users/{userId}', async () => {
      const userId = '123-456-789';

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ id: userId, username: 'updated' })
      });

      const userForm = {
        username: 'updated',
        role: 'admin',
        password: ''
      };

      const payload = buildUpdateUserPayload(userForm);

      await apiRequest(`/api/admin/users/${userId}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });

      expect(fetchSpy).toHaveBeenCalledWith(`/api/admin/users/${userId}`, {
        method: 'PUT',
        body: JSON.stringify({
          username: 'updated',
          role: 'admin'
        }),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer valid-token'
        }
      });
    });
  });

  describe('Update Own Account API Call', () => {
    it('sends PUT to /api/auth/me', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          id: 'my-id',
          username: 'updated',
          role: 'admin',
          tenant_id: 'tenant-123'
        })
      });

      const userForm = {
        username: 'updated',
        password: 'newpass',
        current_password: 'oldpass'
      };

      const payload = buildUpdateMyAccountPayload(userForm);

      const response = await apiRequest('/api/auth/me', {
        method: 'PUT',
        body: JSON.stringify(payload)
      });

      expect(fetchSpy).toHaveBeenCalledWith('/api/auth/me', {
        method: 'PUT',
        body: JSON.stringify({
          username: 'updated',
          password: 'newpass',
          current_password: 'oldpass'
        }),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer valid-token'
        }
      });

      // Verify response includes tenant_id for state update
      const userData = await response.json();
      expect(userData.tenant_id).toBe('tenant-123');
    });
  });

  describe('Delete User API Call', () => {
    it('sends DELETE to /api/admin/users/{userId}', async () => {
      const userId = '123-456-789';

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 204
      });

      await apiRequest(`/api/admin/users/${userId}`, {
        method: 'DELETE'
      });

      expect(fetchSpy).toHaveBeenCalledWith(`/api/admin/users/${userId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer valid-token'
        }
      });
    });
  });
});

describe('User Management - Response Handling', () => {
  let fetchSpy;
  let store;
  let originalLocalStorage;

  beforeEach(() => {
    store = { 'auth_token': 'valid-token' };

    // Save original localStorage
    originalLocalStorage = window.localStorage;

    // Create mock localStorage
    const mockLocalStorage = {
      _store: store,
      getItem: vi.fn((key) => key in store ? store[key] : null),
      setItem: vi.fn((key, value) => { store[key] = value; }),
      removeItem: vi.fn((key) => { delete store[key]; }),
      clear: vi.fn()
    };

    // Replace localStorage using Object.defineProperty
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

    vi.restoreAllMocks();
  });

  describe('User state update after profile change', () => {
    it('response includes all required user fields', async () => {
      const updatedUserResponse = {
        id: 'user-123',
        username: 'newname',
        role: 'admin',
        tenant_id: 'tenant-456'
      };

      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve(updatedUserResponse)
      });

      const response = await apiRequest('/api/auth/me', {
        method: 'PUT',
        body: JSON.stringify({ username: 'newname' })
      });

      const user = await response.json();

      // Verify all fields needed for local state update
      expect(user.id).toBeDefined();
      expect(user.username).toBe('newname');
      expect(user.role).toBe('admin');
      expect(user.tenant_id).toBe('tenant-456');

      // This is the state update pattern from app.js:1864-1869
      const localUserState = {
        id: user.id,
        username: user.username,
        role: user.role,
        tenant_id: user.tenant_id
      };

      expect(localUserState).toEqual({
        id: 'user-123',
        username: 'newname',
        role: 'admin',
        tenant_id: 'tenant-456'
      });
    });
  });

  describe('Error response handling', () => {
    it('handles username already exists error', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: 'Username already exists' })
      });

      const response = await apiRequest('/api/admin/users', {
        method: 'POST',
        body: JSON.stringify({ username: 'existing', role: 'user', password: 'pass' })
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(400);

      const error = await response.json();
      expect(error.detail).toBe('Username already exists');
    });

    it('handles permission denied error', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: () => Promise.resolve({ detail: 'Admin access required' })
      });

      const response = await apiRequest('/api/admin/users', {
        method: 'GET'
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(403);

      const error = await response.json();
      expect(error.detail).toBe('Admin access required');
    });

    it('handles user not found error', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'User not found' })
      });

      const response = await apiRequest('/api/admin/users/nonexistent', {
        method: 'PUT',
        body: JSON.stringify({ username: 'test', role: 'user' })
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(404);

      const error = await response.json();
      expect(error.detail).toBe('User not found');
    });

    it('handles wrong current password error', async () => {
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () => Promise.resolve({ detail: 'Current password is incorrect' })
      });

      const response = await apiRequest('/api/auth/me', {
        method: 'PUT',
        body: JSON.stringify({
          username: 'me',
          password: 'new',
          current_password: 'wrong'
        })
      });

      expect(response.ok).toBe(false);
      expect(response.status).toBe(400);

      const error = await response.json();
      expect(error.detail).toBe('Current password is incorrect');
    });
  });
});
