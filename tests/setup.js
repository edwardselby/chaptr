/**
 * Vitest setup file
 * Runs before all tests to configure the browser environment
 */

import Dexie from 'dexie';

// Make Dexie available globally to match production environment
// In production, Dexie is loaded via CDN: <script src="...dexie.min.js"></script>
window.Dexie = Dexie;
