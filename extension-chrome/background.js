const PLAYER = "http://localhost:8080/player/";
const HOSTED_PLAYER = "https://multiwebblayer.mwplay.workers.dev/";
const NATIVE_HOST = "com.streambridge.player";
const LOCAL_API = "http://127.0.0.1:8080";

// Sekme ikonuna tiklayinca: mevcut sayfayi player'da ac
chrome.action.onClicked.addListener(tab => {
  if (tab?.url) openInPlayer(tab.url);
});

// Sag tik menusu: sayfa veya secili link uzerinde
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "sb-page",
    title: "StreamBridge ile reklamsız izle",
    contexts: ["page", "link"],
    documentUrlPatterns: [
      "*://*.twitch.tv/*", "*://*.kick.com/*",
      "*://*.youtube.com/*", "*://youtu.be/*"
    ],
    targetUrlPatterns: [
      "*://*.twitch.tv/*", "*://*.kick.com/*",
      "*://*.youtube.com/*", "*://youtu.be/*"
    ]
  });
});

chrome.contextMenus.onClicked.addListener(info => {
  const url = info.linkUrl || info.pageUrl;
  if (url) openInPlayer(url);
});

function openInPlayer(url) {
  chrome.tabs.create({ url: PLAYER + "?url=" + encodeURIComponent(url) });
}

function platformUrl(info) {
  if (info.platform === 'youtube') return `https://www.youtube.com/watch?v=${info.id}`;
  return `https://${info.platform}.com/${info.id}`;
}

function base64Url(value) {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  bytes.forEach(byte => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'SB_LOCAL_FETCH') {
    const path = String(message.path || '');
    const allowed = /^\/api\/(?:system\/health|stream\/(?:twitch|kick|youtube)\/@?[A-Za-z0-9_.-]{2,100})$/;
    if (!allowed.test(path)) {
      sendResponse({ ok: false, error: 'Yerel API yolu reddedildi' });
      return false;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    fetch(LOCAL_API + path, { cache: 'no-store', signal: controller.signal })
      .then(async response => {
        const body = await response.text();
        sendResponse({ ok: response.ok, status: response.status, body });
      })
      .catch(error => sendResponse({
        ok: false,
        unavailable: true,
        error: error.name === 'AbortError' ? 'Yerel servis zaman aşımı' : error.message
      }))
      .finally(() => clearTimeout(timeout));
    return true;
  }
  if (message?.type === 'SB_OPEN_HOSTED') {
    const info = message.info;
    const payload = base64Url(JSON.stringify({
      platform: info.platform,
      id: info.id,
      title: info.id,
      url: platformUrl(info)
    }));
    chrome.tabs.create({ url: `${HOSTED_PLAYER}?sb_import=${payload}` });
    sendResponse({ ok: true });
    return false;
  }
  if (message?.type === 'SB_OPEN_NATIVE') {
    chrome.runtime.sendNativeMessage(NATIVE_HOST, {
      action: 'play',
      platform: message.info.platform,
      id: message.info.id,
      url: message.sourceUrl
    }, response => {
      if (chrome.runtime.lastError) {
        sendResponse({
          ok: false,
          error: 'Native StreamBridge uygulaması kurulu değil: ' + chrome.runtime.lastError.message
        });
      } else sendResponse(response?.ok === false ? response : { ok: true });
    });
    return true;
  }
  return false;
});
