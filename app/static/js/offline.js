async function syncToDevice() {
  const el = document.getElementById('sync-status');
  try {
    const r = await fetch('/api/sync/export');
    if (!r.ok) throw new Error('Sync failed');
    const data = await r.json();
    localStorage.setItem('bizpos_backup', JSON.stringify(data));
    localStorage.setItem('bizpos_backup_at', data.exported_at || new Date().toISOString());
    if (el) el.textContent = 'Saved offline · ' + (data.exported_at || '');
  } catch (e) {
    if (el) el.textContent = e.message;
  }
}
// Auto-sync when online after load
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    if (navigator.onLine && location.pathname.startsWith('/dashboard')) {
      syncToDevice().catch(() => {});
    }
  });
}
