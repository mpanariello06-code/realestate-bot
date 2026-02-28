// client.js — loaded on pages that need additional client-portal logic
// Most page logic is inline in each HTML file for self-containment.
// This file provides shared utilities specific to the client portal.

// Re-export / augment shared utilities from api.js if needed.

// Platform icon helper
function platformIcon(p) {
  const map = {
    facebook: 'facebook', instagram: 'instagram',
    tiktok: 'tiktok', whatsapp: 'whatsapp',
    twitter: 'twitter', x: 'x-twitter',
  };
  return map[(p || '').toLowerCase()] || 'globe';
}

// Auto-refresh helper — call startAutoRefresh(fn, ms) to poll data
function startAutoRefresh(fn, intervalMs = 30000) {
  fn();
  return setInterval(fn, intervalMs);
}

// Export for pages that explicitly include this script
if (typeof module !== 'undefined') {
  module.exports = { platformIcon, startAutoRefresh };
}
