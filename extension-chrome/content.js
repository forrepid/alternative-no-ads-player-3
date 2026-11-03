(() => {
  'use strict';
  if (window.top !== window) return;

  const SERVER = 'http://localhost:8080';
  const IDS = { button: 'sb-toggle-btn', mode: 'sb-player-mode', settings: 'sb-player-settings', player: 'sb-player-wrap' };
  const DEFAULT_HLS_SETTINGS = { profile: 'default', liveSync: 3, liveMax: 0, maxBuffer: 0, backBuffer: 30 };
  const STABLE_HLS_SETTINGS = { profile: 'stable', liveSync: 3, liveMax: 6, maxBuffer: 30, backBuffer: 60 };
  let active = false;
  let original = null;
  let originalDisplay = '';
  let online = false;
  let mode = 'local_iframe';
  let hls = null;
  let lastUrl = location.href;
  let suppressionTimer = null;
  let playerSettings = { ...DEFAULT_HLS_SETTINGS };
  let shadowStatsTimer = null;
  const suppressedElements = new Set();
  const suppressedMedia = new Map();
  const suppressMediaEvent = event => {
    if (!active || event.target.closest?.(`#${IDS.player}`)) return;
    try { event.target.muted = true; event.target.pause(); } catch (_) {}
  };

  function watchInfo() {
    const host = location.hostname.replace(/^www\./, '');
    const path = location.pathname;
    if (host === 'twitch.tv' || host.endsWith('.twitch.tv')) {
      const match = path.match(/^\/([A-Za-z0-9_]{3,25})\/?$/);
      const reserved = new Set(['directory', 'downloads', 'settings', 'subscriptions',
        'wallet', 'friends', 'inventory', 'drops', 'moderator', 'dashboard', 'prime',
        'turbo', 'jobs', 'store', 'search', 'p', 'videos', 'clips']);
      return match && !reserved.has(match[1].toLowerCase())
        ? { platform: 'twitch', id: match[1] } : null;
    }
    if (host === 'kick.com' || host.endsWith('.kick.com')) {
      const match = path.match(/^\/([A-Za-z0-9_-]{2,25})\/?$/);
      const reserved = new Set(['categories', 'category', 'about', 'support', 'privacy',
        'terms', 'settings', 'auth', 'login', 'signup', 'store', 'rewards', 'search',
        'videos', 'clips']);
      return match && !reserved.has(match[1].toLowerCase())
        ? { platform: 'kick', id: match[1] } : null;
    }
    if (host === 'youtube.com' || host.endsWith('.youtube.com')) {
      const id = path === '/watch' ? new URLSearchParams(location.search).get('v') : null;
      return id ? { platform: 'youtube', id } : null;
    }
    return null;
  }

  function findOriginalPlayer() {
    const pick = list => list.map(selector => document.querySelector(selector)).find(Boolean);
    if (location.hostname.includes('twitch.tv')) {
      return pick(['.channel-root__player-container', '[data-a-target="video-player"]',
        '.video-player', '.persistent-player']);
    }
    if (location.hostname.includes('kick.com')) {
      const mediaRoot = findLargestMediaRoot();
      if (mediaRoot) return mediaRoot;
      const found = pick(['.video-player-container', '#video-player',
        'div[class*="player-container"]', 'div[class*="video-player"]', '.vjs-tech']);
      return found?.matches('video')
        ? found.closest('.video-player-container, #video-player, [class*="player-container"], [class*="video-player"]') || found.parentElement
        : found;
    }
    return pick(['#movie_player', '#player-container', '#ytd-player', '#player']);
  }

  function findLargestMediaRoot() {
    const videos = [...document.querySelectorAll('video')]
      .map(video => ({ video, rect: video.getBoundingClientRect() }))
      .filter(item => item.rect.width > 240 && item.rect.height > 135)
      .sort((a, b) => b.rect.width * b.rect.height - a.rect.width * a.rect.height);
    if (!videos.length) return null;
    const { video, rect } = videos[0];
    let root = video.parentElement || video;
    let parent = video.parentElement;
    for (let depth = 0; parent && depth < 12; depth += 1, parent = parent.parentElement) {
      if (parent === document.body || parent === document.documentElement) break;
      const parentRect = parent.getBoundingClientRect();
      const sameVisualArea = parentRect.width >= rect.width * 0.9 &&
        parentRect.width <= rect.width * 1.2 &&
        parentRect.height >= rect.height * 0.9 &&
        parentRect.height <= rect.height * 1.35;
      if (!sameVisualArea) break;
      root = parent;
    }
    return root;
  }

  function hideOriginalPlayer() {
    original = findOriginalPlayer();
    if (!original) return false;
    originalDisplay = original.style.display;
    suppressPlatformPlayback();
    document.addEventListener('play', suppressMediaEvent, true);
    suppressionTimer = window.setInterval(suppressPlatformPlayback, 250);
    return true;
  }

  function suppressPlatformPlayback() {
    const container = findOriginalPlayer();
    if (container && container.id !== IDS.player && !container.closest(`#${IDS.player}`)) {
      const className = mode === 'standalone' && container === original
        ? 'sb-original-player-mounted'
        : 'sb-original-player-hidden';
      container.classList.add(className);
      suppressedElements.add(container);
    }
    document.querySelectorAll('video, audio').forEach(media => {
      if (media.closest(`#${IDS.player}`)) return;
      try {
        if (!suppressedMedia.has(media)) {
          suppressedMedia.set(media, { muted: media.muted, volume: media.volume });
        }
        media.muted = true;
        media.volume = 0;
        media.pause();
      } catch (_) {}
    });
  }

  function restoreOriginalPlayer() {
    if (suppressionTimer) window.clearInterval(suppressionTimer);
    suppressionTimer = null;
    document.removeEventListener('play', suppressMediaEvent, true);
    suppressedElements.forEach(element => {
      element.classList.remove('sb-original-player-hidden', 'sb-original-player-mounted');
    });
    suppressedElements.clear();
    suppressedMedia.forEach((state, media) => {
      try { media.muted = state.muted; media.volume = state.volume; } catch (_) {}
    });
    suppressedMedia.clear();
    if (!original) return;
    original.style.display = originalDisplay;
    original = null;
  }

  function destroyHls() {
    if (hls) hls.destroy();
    hls = null;
    if (shadowStatsTimer) window.clearInterval(shadowStatsTimer);
    shadowStatsTimer = null;
  }

  function getHlsConfig() {
    const config = {
      liveSyncDurationCount: Number(playerSettings.liveSync) || 3,
      enableWorker: true,
      lowLatencyMode: false,
      backBufferLength: Number(playerSettings.backBuffer) || 30,
      fetchSetup: (context, init) => {
        try { return new Request(context.url, { ...init, targetAddressSpace: 'local' }); }
        catch (_) { return new Request(context.url, init); }
      }
    };
    const liveMax = Number(playerSettings.liveMax);
    if (liveMax > config.liveSyncDurationCount) config.liveMaxLatencyDurationCount = liveMax;
    const maxBuffer = Number(playerSettings.maxBuffer);
    if (maxBuffer > 0) {
      config.maxBufferLength = maxBuffer;
      config.maxMaxBufferLength = Math.max(maxBuffer * 2, 60);
    }
    return config;
  }

  function closePlayer(update = true) {
    destroyHls();
    restoreOriginalPlayer();
    document.getElementById(IDS.player)?.remove();
    active = false;
    if (update) updateButton();
  }

  function iframeUrl(info) {
    const key = info.platform === 'youtube' ? 'video' : 'channel';
    return `${SERVER}/player/?platform=${info.platform}&${key}=${encodeURIComponent(info.id)}`;
  }

  function openIframe(host, info) {
    const iframe = document.createElement('iframe');
    iframe.src = iframeUrl(info);
    iframe.allow = 'autoplay; fullscreen; picture-in-picture';
    iframe.title = 'StreamBridge Player';
    host.appendChild(iframe);
  }

  function openStandalone(host, info) {
    const root = host.attachShadow({ mode: 'open' });
    renderShadow(root);
    const video = root.querySelector('video');
    const quality = root.querySelector('.quality');
    video.remove();
    quality.remove();
    root.querySelector('.return').addEventListener('click', () => closePlayer());
    const iframe = document.createElement('iframe');
    iframe.allow = 'autoplay; fullscreen; picture-in-picture; encrypted-media';
    iframe.style.cssText = 'width:100%;height:100%;border:0;background:#000';
    if (info.platform === 'twitch') {
      iframe.src = `https://player.twitch.tv/?channel=${encodeURIComponent(info.id)}` +
        `&parent=${encodeURIComponent(location.hostname)}&autoplay=true&muted=true`;
    } else if (info.platform === 'youtube') {
      iframe.src = `https://www.youtube.com/embed/${encodeURIComponent(info.id)}` +
        '?autoplay=1&mute=1&playsinline=1';
    } else {
      iframe.src = `https://player.kick.com/${encodeURIComponent(info.id)}` +
        '?autoplay=true&muted=true';
    }
    root.querySelector('.shell').prepend(iframe);
    setStatus(root, `Standalone · ${info.platform} / ${info.id}`);
  }

  function sendAlternative(type, info) {
    chrome.runtime.sendMessage({ type, info, sourceUrl: location.href }, response => {
      if (chrome.runtime.lastError) return toast(chrome.runtime.lastError.message);
      if (!response?.ok) toast(response?.error || 'Yöntem başlatılamadı');
    });
  }

  function renderShadow(root) {
    root.innerHTML = `<style>
      :host{display:block;width:100%;height:100%;background:#000}
      .shell{width:100%;height:100%;position:relative;background:#000;color:#fff;
        font:500 13px system-ui,sans-serif;overflow:hidden}
      video{width:100%;height:100%;display:block;background:#000}
      .bar{position:absolute;top:0;left:0;right:0;z-index:2;display:flex;align-items:center;
        gap:10px;padding:9px 12px;background:linear-gradient(rgba(0,0,0,.82),transparent)}
      .brand{font-weight:750;color:#bf94ff}.status{flex:1;overflow:hidden;
        text-overflow:ellipsis;white-space:nowrap}.status.error{color:#ff7b7b}
      .stats{position:absolute;left:12px;bottom:48px;z-index:3;max-width:70%;padding:6px 8px;
        color:#eee;background:rgba(12,12,15,.8);border:1px solid #555;border-radius:6px;
        font:11px/1.35 ui-monospace,SFMono-Regular,Consolas,monospace}
      select,button{border:1px solid #555;border-radius:6px;background:#242429;color:#fff;
        padding:5px 8px;font:inherit;cursor:pointer}button:hover,select:hover{background:#38383f}
    </style><div class="shell"><video controls autoplay muted playsinline></video><div class="stats">İstatistik hazırlanıyor…</div><div class="bar">
      <span class="brand">StreamBridge</span><span class="status">Yayın bilgisi alınıyor…</span>
      <select class="quality" title="Kalite"><option value="-1">Otomatik</option></select>
      <button class="return" type="button">Platforma dön</button></div></div>`;
  }

  function setStatus(root, text, error = false) {
    const status = root.querySelector('.status');
    status.textContent = text;
    status.classList.toggle('error', error);
  }

  function startShadowStats(root, video, stream) {
    const box = root.querySelector('.stats');
    if (shadowStatsTimer) window.clearInterval(shadowStatsTimer);
    const render = () => {
      if (!hls) return;
      const level = hls.levels?.[hls.currentLevel] || hls.levels?.[hls.loadLevel];
      const buffer = video.buffered.length ? Math.max(0, video.buffered.end(video.buffered.length - 1) - video.currentTime) : 0;
      const latency = Number.isFinite(hls.latency) ? `${hls.latency.toFixed(1)} sn` : '—';
      const quality = level ? `${level.height || '?'}p · ${Math.round((level.bitrate || 0) / 1000)} kbps` : 'Otomatik';
      box.textContent = `Akış: ${quality} | Tampon: ${buffer.toFixed(1)} sn | Gecikme: ${latency} | ${stream.title || stream.channel || ''}`;
    };
    render(); shadowStatsTimer = window.setInterval(render, 1000);
  }

  function backgroundLocalJson(path) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: 'SB_LOCAL_FETCH', path }, response => {
        if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
        if (!response?.ok) {
          const error = new Error(response?.error || `Yerel API ${response?.status || 'hatası'}`);
          error.unavailable = Boolean(response?.unavailable);
          return reject(error);
        }
        try { resolve(JSON.parse(response.body)); }
        catch (_) { reject(new Error('Yerel API geçersiz JSON döndürdü')); }
      });
    });
  }

  function localRequest(url, init = {}) {
    try {
      return fetch(new Request(url, { ...init, targetAddressSpace: 'local' }));
    } catch (_) {
      return fetch(url, init);
    }
  }

  async function localJson(path) {
    try {
      return await backgroundLocalJson(path);
    } catch (backgroundError) {
      const response = await localRequest(SERVER + path, { cache: 'no-store' });
      if (!response.ok) {
        throw new Error(response.status === 404 ? 'Yayın çevrimdışı' : `Yerel API ${response.status}`);
      }
      try { return await response.json(); }
      catch (_) { throw backgroundError; }
    }
  }

  async function ensureLocalNetworkPermission() {
    try {
      const response = await localRequest(`${SERVER}/api/system/health`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`Yerel servis HTTP ${response.status}`);
      return true;
    } catch (error) {
      throw new Error(
        'Chrome yerel ağ erişimine izin vermedi. Adres çubuğundaki yerel ağ iznini açın. ' +
        `(${error.message})`);
    }
  }

  async function openShadow(host, info) {
    const root = host.attachShadow({ mode: 'open' });
    renderShadow(root);
    root.querySelector('.return').addEventListener('click', () => closePlayer());
    const video = root.querySelector('video');
    try {
      await ensureLocalNetworkPermission();
      const stream = await localJson(
        `/api/stream/${info.platform}/${encodeURIComponent(info.id)}`);
      if (!stream.master_playlist) throw new Error('Oynatma listesi bulunamadı');
      const source = new URL(stream.master_playlist, SERVER).href;
      setStatus(root, stream.title || `${info.platform} / ${info.id}`);

      if (globalThis.Hls?.isSupported()) {
        hls = new globalThis.Hls(getHlsConfig());
        hls.on(globalThis.Hls.Events.MANIFEST_PARSED, (_, data) => {
          const quality = root.querySelector('.quality');
          data.levels.forEach((level, index) => {
            const option = document.createElement('option');
            option.value = String(index);
            option.textContent = level.height ? `${level.height}p` : `${Math.round(level.bitrate / 1000)} kbps`;
            quality.appendChild(option);
          });
          video.play().catch(() => {});
        });
        hls.on(globalThis.Hls.Events.ERROR, (_, data) => {
          if (!data.fatal || !hls) return;
          if (data.type === globalThis.Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
          else if (data.type === globalThis.Hls.ErrorTypes.MEDIA_ERROR) hls.recoverMediaError();
          else { setStatus(root, `Oynatma hatası: ${data.details}`, true); destroyHls(); }
        });
        root.querySelector('.quality').addEventListener('change', event => {
          if (hls) hls.currentLevel = Number(event.target.value);
        });
        hls.loadSource(source);
        hls.attachMedia(video);
        startShadowStats(root, video, stream);
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        root.querySelector('.quality').hidden = true;
        video.src = source;
        video.play().catch(() => {});
      } else throw new Error('Bu tarayıcı HLS oynatmayı desteklemiyor');
    } catch (error) {
      setStatus(root, error.message || 'Yayın yüklenemedi', true);
    }
  }

  function openPlayer(info) {
    if (mode === 'hosted') {
      sendAlternative('SB_OPEN_HOSTED', info);
      return;
    }
    if (mode === 'native') {
      sendAlternative('SB_OPEN_NATIVE', info);
      return;
    }
    if (mode.startsWith('local_') && !online) {
      return toast('Yerel StreamBridge servisi çevrimdışı');
    }
    if (active) closePlayer(false);
    if (!hideOriginalPlayer()) return toast('Oynatıcı bulunamadı — sayfayı yenileyip dene');
    const host = document.createElement('div');
    host.id = IDS.player;
    if (mode === 'standalone') {
      host.className = 'sb-overlay-player';
      original.classList.add('sb-original-player-mounted');
      suppressedElements.add(original);
      original.appendChild(host);
    } else original.parentElement.insertBefore(host, original);
    active = true;
    updateButton();
    if (mode === 'local_shadow') openShadow(host, info);
    else if (mode === 'standalone') openStandalone(host, info);
    else openIframe(host, info);
  }

  function updateButton() {
    const button = document.getElementById(IDS.button);
    if (!button) return;
    const panelOwnsReturn = active && (mode === 'standalone' || mode === 'local_shadow');
    button.style.display = panelOwnsReturn ? 'none' : '';
    const modeSelect = document.getElementById(IDS.mode);
    if (modeSelect) modeSelect.style.display = panelOwnsReturn ? 'none' : '';
    const localUnavailable = mode.startsWith('local_') && !online;
    button.textContent = active ? '◀ Platforma Dön'
      : localUnavailable ? '▶ Yerel servis çevrimdışı' : '▶ Seçili yöntemle izle';
    button.classList.toggle('sb-active', active);
  }

  function injectControls() {
    if (document.getElementById(IDS.button) || !watchInfo()) return;
    const select = document.createElement('select');
    select.id = IDS.mode;
    select.title = 'StreamBridge oynatıcı yöntemi';
    select.innerHTML = [
      '<option value="local_iframe">1 · Yerel API + Iframe</option>',
      '<option value="local_shadow">2 · Yerel API + Shadow</option>',
      '<option value="standalone">3 · Standalone eklenti</option>',
      '<option value="hosted">4 · MultiWebPlayer Cloud</option>',
      '<option value="native">5 · Native masaüstü</option>'
    ].join('');
    select.value = mode;
    select.addEventListener('change', () => {
      mode = select.value;
      chrome.storage.local.set({ playerMode: mode });
      if (active) openPlayer(watchInfo());
    });
    const button = document.createElement('button');
    button.id = IDS.button;
    button.type = 'button';
    button.addEventListener('click', () => active ? closePlayer() : openPlayer(watchInfo()));
    const settings = document.createElement('button');
    settings.id = IDS.settings;
    settings.type = 'button';
    settings.textContent = '⚙ Ayarlar';
    settings.addEventListener('click', openSettings);
    document.body.append(select, button, settings);
    updateButton();
  }

  function removeControls() {
    document.getElementById(IDS.button)?.remove();
    document.getElementById(IDS.mode)?.remove();
    document.getElementById(IDS.settings)?.remove();
    if (active) closePlayer();
  }

  async function checkServer() {
    try { online = Boolean(await localJson('/api/system/health')); }
    catch (_) { online = false; }
    updateButton();
  }

  function refresh() {
    const info = watchInfo();
    if (!info) return removeControls();
    if (active) openPlayer(info);
    injectControls();
  }

  function toast(message) {
    const node = document.createElement('div');
    node.textContent = message;
    node.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:2147483647;' +
      'background:#18181b;color:#fff;padding:12px 18px;border-radius:10px;' +
      'font:500 14px system-ui;box-shadow:0 4px 14px rgba(0,0,0,.5)';
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 3500);
  }

  function openSettings() {
    document.getElementById('sb-settings-panel')?.remove();
    const panel = document.createElement('section');
    panel.id = 'sb-settings-panel';
    panel.innerHTML = `<strong>StreamBridge oynatma ayarları</strong>
      <label>Profil <select data-key="profile"><option value="default">Varsayılan</option><option value="stable">Stabil</option><option value="custom">Kişisel</option></select></label>
      <label>Canlı senkron <input data-key="liveSync" type="number" min="1" max="10"></label>
      <label>Azami gecikme <input data-key="liveMax" type="number" min="0" max="20"></label>
      <label>İleri tampon (sn) <input data-key="maxBuffer" type="number" min="0" max="120"></label>
      <label>Geri tampon (sn) <input data-key="backBuffer" type="number" min="10" max="300"></label>
      <small>Stabil: 3/6 segment, 30 sn ileri ve 60 sn geri tampon. Yeni oynatmada uygulanır.</small>
      <div><button data-action="save">Kaydet</button><button data-action="close">Kapat</button></div>`;
    panel.querySelectorAll('[data-key]').forEach(field => { field.value = playerSettings[field.dataset.key]; });
    panel.querySelector('[data-key="profile"]').addEventListener('change', event => {
      const preset = event.target.value === 'stable' ? STABLE_HLS_SETTINGS : event.target.value === 'default' ? DEFAULT_HLS_SETTINGS : null;
      if (!preset) return;
      panel.querySelectorAll('[data-key]').forEach(field => { field.value = preset[field.dataset.key]; });
    });
    panel.querySelector('[data-action="save"]').addEventListener('click', () => {
      const next = {};
      panel.querySelectorAll('[data-key]').forEach(field => { next[field.dataset.key] = field.dataset.key === 'profile' ? field.value : Number(field.value); });
      playerSettings = { ...DEFAULT_HLS_SETTINGS, ...next };
      chrome.storage.local.set({ playerHlsSettings: playerSettings });
      panel.remove();
      toast('Ayarlar kaydedildi; sonraki oynatmada uygulanacak.');
    });
    panel.querySelector('[data-action="close"]').addEventListener('click', () => panel.remove());
    document.body.appendChild(panel);
  }

  chrome.storage.local.get({ playerMode: 'local_iframe', playerHlsSettings: DEFAULT_HLS_SETTINGS }, stored => {
    const modes = new Set(['local_iframe', 'local_shadow', 'standalone', 'hosted', 'native']);
    mode = modes.has(stored.playerMode) ? stored.playerMode : 'local_iframe';
    playerSettings = { ...DEFAULT_HLS_SETTINGS, ...stored.playerHlsSettings };
    injectControls();
  });
  checkServer();
  setInterval(checkServer, 30000);
  setTimeout(refresh, 1500);
  setInterval(() => {
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    setTimeout(refresh, 1200);
  }, 600);
})();
