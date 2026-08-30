(() => {
  'use strict';
  const params = new URLSearchParams(location.search);
  const encoded = params.get('sb_import');
  if (!encoded) return;
  try {
    const normalized = encoded.replace(/-/g, '+').replace(/_/g, '/');
    const item = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')));
    if (!['twitch', 'kick', 'youtube'].includes(item.platform) || !item.url) return;
    const settings = JSON.parse(localStorage.getItem('multiweb-settings') || '{}');
    settings.remember = true;
    localStorage.setItem('multiweb-settings', JSON.stringify(settings));
    const streams = JSON.parse(localStorage.getItem('multiweb-streams') || '[]');
    if (!streams.some(stream => stream.url === item.url)) {
      streams.push({
        uid: crypto.randomUUID(), url: item.url, title: item.title || item.id,
        size: 100, mode: 'official', muted: true, paused: false,
        platformUrl: item.url, order: streams.length
      });
      localStorage.setItem('multiweb-streams', JSON.stringify(streams));
    }
    history.replaceState({}, '', location.pathname);
    location.reload();
  } catch (error) {
    console.warn('StreamBridge hosted import failed', error);
  }
})();
