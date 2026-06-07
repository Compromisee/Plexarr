/* Plexarr Docs Site JS */

function $(sel) { return document.querySelector(sel); }
function $$(sel) { return document.querySelectorAll(sel); }

// Mobile sidebar toggle
function toggleSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('sidebarOverlay');
  if (!sb) return;
  sb.classList.toggle('open');
  if (ov) ov.classList.toggle('show');
  document.body.style.overflow = sb.classList.contains('open') ? 'hidden' : '';
}

// Step wizard
function goStep(n) {
  const steps = document.querySelectorAll('.wizard-step');
  const panels = document.querySelectorAll('.step-panel');
  steps.forEach((s, i) => {
    s.classList.remove('active', 'done');
    if (i < n) s.classList.add('done');
    if (i === n) s.classList.add('active');
  });
  panels.forEach((p, i) => {
    p.classList.remove('active');
    if (i === n) p.classList.add('active');
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// LAN Detection
async function detectLan() {
  const status = document.getElementById('lanStatus');
  const ip = document.getElementById('lanIp');
  const server = document.getElementById('lanServer');
  const icon = document.getElementById('lanIcon');
  if (!status) return;

  status.innerHTML = '<span class="micon">wifi_find</span> SCANNING...';
  status.className = 'lan-status';
  await sleep(800);

  try {
    const r = await fetch('http://' + location.hostname + ':8080/health', { mode: 'no-cors', signal: AbortSignal.timeout(2000) });
    status.innerHTML = '<span class="dot online"></span> SERVER DETECTED';
    if (server) server.textContent = 'http://' + location.hostname + ':8080';
    if (ip) ip.textContent = location.hostname;
    if (icon) icon.textContent = 'check_circle';
    return;
  } catch (e) { }

  const host = location.hostname;
  const isLocal = /^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.)/.test(host) || host === 'localhost' || host === '127.0.0.1';
  if (isLocal) {
    status.innerHTML = '<span class="dot warn"></span> LAN DETECTED (SERVER NOT FOUND)';
    if (server) server.textContent = 'NOT FOUND ON :8080';
    if (ip) ip.textContent = host;
    if (icon) icon.textContent = 'warning';
  } else {
    status.innerHTML = '<span class="dot offline"></span> NO LAN SERVER';
    if (server) server.textContent = 'NONE';
    if (ip) ip.textContent = host;
    if (icon) icon.textContent = 'cancel';
  }
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// Copy to clipboard
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast('Copied to clipboard', 'success');
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
    showToast('Copied to clipboard', 'success');
  });
}

// Toast
function showToast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const t = document.createElement('div');
  t.className = 'toast ' + (type === 'error' ? 'error' : type === 'success' ? 'success' : type === 'warn' ? 'warn' : '');
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    t.style.transform = 'translateX(100%) scale(0.95)';
    setTimeout(() => t.remove(), 300);
  }, 3000);
}

// Smooth parallax on scroll
let ticking = false;
window.addEventListener('scroll', () => {
  if (!ticking) {
    window.requestAnimationFrame(() => {
      const scrolled = window.pageYOffset;
      const p1 = document.querySelector('.parallax-1');
      const p2 = document.querySelector('.parallax-2');
      const p3 = document.querySelector('.parallax-3');
      if (p1) p1.style.transform = `translateY(${scrolled * 0.25}px)`;
      if (p2) p2.style.transform = `translateY(${scrolled * 0.12}px)`;
      if (p3) p3.style.transform = `translateY(${scrolled * 0.06}px)`;
      ticking = false;
    });
    ticking = true;
  }
});

// Active sidebar link
(function initNav() {
  const path = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.sidebar-nav .nav-link').forEach(a => {
    const href = a.getAttribute('href');
    if (href && (href === path || (path === '' && href === 'index.html'))) {
      a.classList.add('active');
    }
  });
})();

// Scroll reveal observer
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      revealObserver.unobserve(e.target);
    }
  });
}, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

// Export globals
window.toggleSidebar = toggleSidebar;
window.goStep = goStep;
window.detectLan = detectLan;
window.copyToClipboard = copyToClipboard;
window.showToast = showToast;
