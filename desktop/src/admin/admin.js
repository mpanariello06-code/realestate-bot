// admin.js — loaded on pages that need additional admin-portal logic
// Most page logic is inline in each HTML file for self-containment.

// ── Admin auth helpers ──────────────────────────────────────────────────────

async function getAdminToken() {
  return await window.electronAPI.storeGet('admin_token');
}

async function adminRequest(method, path, body = null) {
  const token = await getAdminToken();
  const result = await window.electronAPI.apiRequest(method, path, body, token);
  if (result.status === 401) {
    await window.electronAPI.storeDelete('admin_token');
    window.location.href = 'login.html';
  }
  return result;
}

async function checkAdminAuth() {
  const token = await getAdminToken();
  if (!token) { window.location.href = 'login.html'; return null; }
  const res = await adminRequest('GET', '/auth/me');
  if (!res.ok || res.data.role !== 'admin') {
    await window.electronAPI.storeDelete('admin_token');
    window.location.href = 'login.html';
    return null;
  }
  return res.data;
}

// ── CSV Export ───────────────────────────────────────────────────────────────

function exportToCSV(data, filename) {
  if (!data || !data.length) { showToast('warning', 'No data to export'); return; }
  const keys = Object.keys(data[0]);
  const rows = [keys.join(','), ...data.map(row => keys.map(k => JSON.stringify(row[k] ?? '')).join(','))];
  const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename || 'export.csv'; a.click();
  URL.revokeObjectURL(url);
}

if (typeof module !== 'undefined') {
  module.exports = { adminRequest, checkAdminAuth, exportToCSV };
}
