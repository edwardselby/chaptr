import { defineConfig } from 'vitest/config';
import { playwright } from '@vitest/browser-playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  test: {
    // Use browser mode for real browser testing (IndexedDB, Alpine.js)
    browser: {
      enabled: true,
      instances: [
        {
          browser: 'chromium',
          provider: playwright(),
        },
      ],
      // Headless in CI, visible browser for local debugging
      headless: process.env.CI !== undefined ? true : false,
    },

    // Setup file to configure browser environment
    setupFiles: ['./tests/setup.js'],

    // Global test APIs (describe, it, expect) without imports
    globals: true,

    // Test file patterns
    include: ['tests/**/*.test.js'],

    // Coverage configuration
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: [
        'tests/**',
        'node_modules/**',
        'static/sw.js',
      ],
    },

    // Resolve aliases to match project structure
    alias: {
      '@': path.resolve(__dirname, './static/js'),
    },
  },

  // Resolve static files for browser mode
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './static/js'),
    },
  },
});
