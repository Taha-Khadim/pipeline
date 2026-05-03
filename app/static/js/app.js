/* =========================================================
   LumoraCode Client Hunter — App JS
   ========================================================= */

// --- Theme ---
function toggleTheme() {
  const html = document.documentElement;
  if (html.classList.contains('dark')) {
    html.classList.remove('dark');
    localStorage.theme = 'light';
  } else {
    html.classList.add('dark');
    localStorage.theme = 'dark';
  }
  window.dispatchEvent(new CustomEvent('theme-changed'));
}

function isDark() {
  return document.documentElement.classList.contains('dark');
}

// --- Toasts ---
function toastManager() {
  return {
    toasts: [],
    addToast(detail) {
      const id = Date.now();
      this.toasts.push({ id, message: detail.message, type: detail.type || 'info', visible: true });
      setTimeout(() => {
        const t = this.toasts.find(t => t.id === id);
        if (t) t.visible = false;
        setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 300);
      }, 4000);
    }
  };
}

function toast(message, type = 'info') {
  window.dispatchEvent(new CustomEvent('toast', { detail: { message, type } }));
}

// --- API helper ---
async function api(url, options = {}) {
  const defaults = { headers: { 'Content-Type': 'application/json' } };
  const res = await fetch(url, { ...defaults, ...options });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }));
    toast(err.detail || 'Something went wrong', 'error');
    throw new Error(err.detail);
  }
  return res.json();
}

// --- Status badge ---
function statusBadge(status) {
  const s = status.toLowerCase();
  const labels = {
    found: 'Found', researched: 'Researched', contacted: 'Contacted',
    responded: 'Responded', call_booked: 'Call Booked', proposal_sent: 'Proposal Sent',
    closed_won: 'Closed Won', closed_lost: 'Closed Lost',
  };
  return `<span class="badge badge-${s}">${labels[s] || status}</span>`;
}

function timeAgo(dateStr) {
  const now = new Date();
  const date = new Date(dateStr);
  const secs = Math.floor((now - date) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

// --- Chart.js theme integration ---
function getChartColors() {
  const dark = isDark();
  return {
    text: dark ? '#a0a0ab' : '#57534e',
    textMuted: dark ? '#52525b' : '#a8a29e',
    grid: dark ? '#1e1e21' : '#eae9e4',
    bg: dark ? '#111113' : '#ffffff',
    accent: dark ? '#2dd4bf' : '#0d9488',
    accentLight: dark ? 'rgba(45,212,191,0.15)' : 'rgba(13,148,136,0.1)',
    palette: dark
      ? ['#38bdf8', '#a78bfa', '#fbbf24', '#34d399', '#f87171', '#22d3ee', '#c084fc', '#fb923c']
      : ['#0284c7', '#7c3aed', '#d97706', '#16a34a', '#dc2626', '#0891b2', '#9333ea', '#ea580c'],
    status: {
      FOUND: dark ? '#38bdf8' : '#0284c7',
      RESEARCHED: dark ? '#a78bfa' : '#7c3aed',
      CONTACTED: dark ? '#fbbf24' : '#d97706',
      RESPONDED: dark ? '#34d399' : '#16a34a',
      CALL_BOOKED: dark ? '#22d3ee' : '#0891b2',
      PROPOSAL_SENT: dark ? '#c084fc' : '#9333ea',
      CLOSED_WON: dark ? '#4ade80' : '#22c55e',
      CLOSED_LOST: dark ? '#f87171' : '#dc2626',
    }
  };
}

Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.color = isDark() ? '#a0a0ab' : '#57534e';
Chart.defaults.borderColor = isDark() ? '#1e1e21' : '#eae9e4';

window.addEventListener('theme-changed', () => {
  const c = getChartColors();
  Chart.defaults.color = c.text;
  Chart.defaults.borderColor = c.grid;
});
