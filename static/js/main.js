// ── Flash message auto-dismiss ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    setTimeout(() => dismissAlert(alert), 5000);
    const closeBtn = alert.querySelector('.alert-close');
    if (closeBtn) closeBtn.addEventListener('click', () => dismissAlert(alert));
  });

  function dismissAlert(el) {
    el.style.transition = 'opacity 0.4s, transform 0.4s';
    el.style.opacity = '0';
    el.style.transform = 'translateX(100%)';
    setTimeout(() => el.remove(), 400);
  }

  // ── Mobile sidebar toggle ───────────────────────────────────────────────
  const menuBtn = document.getElementById('mobile-menu-btn');
  const sidebar = document.querySelector('.sidebar');
  if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', () => sidebar.classList.toggle('open'));
    document.addEventListener('click', (e) => {
      if (!sidebar.contains(e.target) && !menuBtn.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    });
  }

  // ── Due-date countdown timers ───────────────────────────────────────────
  document.querySelectorAll('[data-due-utc]').forEach(el => {
    const dueTimestamp = parseInt(el.dataset.dueUtc, 10) * 1000;
    updateCountdown(el, dueTimestamp);
    setInterval(() => updateCountdown(el, dueTimestamp), 60000);
  });

  function updateCountdown(el, dueTs) {
    const now = Date.now();
    const diff = dueTs - now;
    if (diff <= 0) {
      el.textContent = 'Overdue';
      el.classList.add('overdue');
      return;
    }
    const days    = Math.floor(diff / 86400000);
    const hours   = Math.floor((diff % 86400000) / 3600000);
    const minutes = Math.floor((diff % 3600000) / 60000);
    if (days > 0)       el.textContent = `${days}d ${hours}h left`;
    else if (hours > 0) el.textContent = `${hours}h ${minutes}m left`;
    else                el.textContent = `${minutes}m left`;
  }

  // ── Confirm dangerous actions ───────────────────────────────────────────
  document.querySelectorAll('[data-confirm]').forEach(btn => {
    btn.addEventListener('click', function (e) {
      const msg = this.dataset.confirm || 'Are you sure?';
      if (!confirm(msg)) e.preventDefault();
    });
  });

  // ── Submission form link preview ────────────────────────────────────────
  const linkInput = document.getElementById('content_link');
  const linkPreview = document.getElementById('link-preview');
  if (linkInput && linkPreview) {
    linkInput.addEventListener('input', function () {
      const val = this.value.trim();
      if (val.startsWith('http')) {
        linkPreview.textContent = '🔗 ' + val;
        linkPreview.style.display = 'block';
      } else {
        linkPreview.style.display = 'none';
      }
    });
  }

  // ── Animate stat cards on load ──────────────────────────────────────────
  document.querySelectorAll('.stat-value[data-target]').forEach(el => {
    const target = parseInt(el.dataset.target, 10);
    if (isNaN(target)) return;
    let current = 0;
    const step = Math.max(1, Math.floor(target / 40));
    const timer = setInterval(() => {
      current = Math.min(current + step, target);
      el.textContent = current + (el.dataset.suffix || '');
      if (current >= target) clearInterval(timer);
    }, 20);
  });
});
