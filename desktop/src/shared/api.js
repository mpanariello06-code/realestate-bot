// Shared API client - used by both portals via inline <script> or module
// All calls routed through Electron's contextBridge (window.electronAPI)

async function getToken() {
  return await window.electronAPI.storeGet('auth_token');
}

async function apiRequest(method, path, body = null) {
  const token = await getToken();
  const result = await window.electronAPI.apiRequest(method, path, body, token);
  if (result.status === 401) {
    await window.electronAPI.storeDelete('auth_token');
    redirectToLogin();
  }
  return result;
}

function redirectToLogin() {
  const isAdmin = window.location.pathname.includes('/admin/');
  window.location.href = isAdmin ? '../admin/login.html' : '../client/login.html';
}

async function checkAuth(requireAdmin = false) {
  const token = await window.electronAPI.storeGet('auth_token');
  if (!token) { redirectToLogin(); return null; }

  const res = await apiRequest('GET', '/auth/me');
  if (!res.ok) { redirectToLogin(); return null; }

  if (requireAdmin && res.data.role !== 'admin') {
    window.location.href = '../client/login.html';
    return null;
  }
  return res.data;
}

// Toast notification system
function showToast(type, title, subtitle = '', duration = 4000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info', warning: 'fa-triangle-exclamation' };
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <i class="fa-solid ${icons[type] || icons.info} toast-icon"></i>
    <div class="toast-msg">
      <div class="toast-title">${title}</div>
      ${subtitle ? `<div class="toast-sub">${subtitle}</div>` : ''}
    </div>`;

  container.appendChild(toast);

  function fadeOut() {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s';
    setTimeout(() => toast.remove(), 300);
  }

  setTimeout(fadeOut, duration);
}

function formatCurrency(amount) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 }).format(amount);
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatRelative(dateStr) {
  if (!dateStr) return '—';
  const diff = Date.now() - new Date(dateStr);
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function getScoreColor(score) {
  if (score >= 70) return 'var(--success)';
  if (score >= 40) return 'var(--warning)';
  return 'var(--danger)';
}

function getStatusBadge(status) {
  const map = {
    new:          'badge-blue',
    qualified:    'badge-green',
    unqualified:  'badge-red',
    called:       'badge-purple',
    active:       'badge-green',
    inactive:     'badge-gray',
    pending:      'badge-yellow',
    paid:         'badge-green',
    overdue:      'badge-red',
    sold:         'badge-purple',
    'for sale':   'badge-blue',
    'for rent':   'badge-blue',
  };
  const cls = map[status?.toLowerCase()] || 'badge-gray';
  return `<span class="badge ${cls}">${status || '—'}</span>`;
}

function openModal(id) { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});
