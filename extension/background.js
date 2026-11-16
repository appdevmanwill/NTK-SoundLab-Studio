const MAX_STREAMS_PER_TAB = 25;
const MAX_TRANSFER_BYTES = 150 * 1024 * 1024;
const CHUNK_BYTES = 1536 * 1024; // 1.5 MiB base64 chunks
const MIN_MEDIA_BYTES = 8192;

const MEDIA_EXT_RE = /\.(mp3|m4a|aac|wav|flac|ogg|opus|mp4|webm|mov)(?:$|[?#])/i;
const MANIFEST_EXT_RE = /\.(m3u8|mpd)(?:$|[?#])/i;
const IGNORED_EXT_RE = /\.(js|mjs|css|map|png|jpe?g|webp|gif|svg|ico|woff2?|ttf|eot|vtt|srt|html?|txt|xml|json)(?:$|[?#])/i;
const DRM_URL_RE = /(\/license\b|widevine|playready|fairplay|\.key(?:$|[?#])|drm.*challenge)/i;
const STUDIO_HOSTS = new Set(['studio-5090403114-fc98b.web.app', '127.0.0.1', 'localhost']);

const pendingTransfers = new Map();

function sanitizeFileName(name, fallbackExt = 'mp3') {
  const base = String(name || 'Captured_Media')
    .replace(/[<>:"/\\|?*\x00-\x1f]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 90) || 'Captured_Media';
  return base.includes('.') ? base : `${base}.${fallbackExt}`;
}

function inferExtFromMime(mime, fallbackUrl) {
  const clean = String(mime || '').split(';')[0].trim().toLowerCase();
  const byMime = {
    'audio/mpeg': 'mp3',
    'audio/mp3': 'mp3',
    'audio/mp4': 'm4a',
    'audio/m4a': 'm4a',
    'audio/x-m4a': 'm4a',
    'audio/aac': 'aac',
    'audio/x-aac': 'aac',
    'audio/aacp': 'aac',
    'audio/ogg': 'ogg',
    'application/ogg': 'ogg',
    'audio/opus': 'opus',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/wave': 'wav',
    'audio/flac': 'flac',
    'audio/x-flac': 'flac',
    'audio/webm': 'webm',
    'video/mp4': 'mp4',
    'video/webm': 'webm',
    'video/quicktime': 'mov',
    'application/vnd.apple.mpegurl': 'm3u8',
    'application/x-mpegurl': 'm3u8',
    'application/dash+xml': 'mpd'
  };
  if (byMime[clean]) return byMime[clean];
  try {
    const u = new URL(fallbackUrl);
    const m = u.pathname.match(/\.([a-z0-9]{2,5})$/i);
    if (m) return m[1].toLowerCase();
  } catch {}
  return clean.startsWith('video/') ? 'mp4' : 'mp3';
}

function classifyMediaCandidate(url, rawMime, contentLength, resourceType) {
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
  if (STUDIO_HOSTS.has(parsed.hostname.toLowerCase())) return null;
  if (DRM_URL_RE.test(url)) return null;

  const mime = String(rawMime || '').split(';')[0].trim().toLowerCase();
  if (mime.startsWith('text/') || mime.startsWith('image/') || mime.startsWith('font/') || mime === 'application/json' || mime === 'application/javascript') {
    return null;
  }
  if (IGNORED_EXT_RE.test(parsed.pathname)) return null;
  if (contentLength > 0 && contentLength < MIN_MEDIA_BYTES && !MANIFEST_EXT_RE.test(parsed.pathname)) {
    return null;
  }

  const isManifestMime = mime === 'application/vnd.apple.mpegurl' || mime === 'application/x-mpegurl' || mime === 'application/dash+xml';
  const isManifestExt = MANIFEST_EXT_RE.test(parsed.pathname);
  if (isManifestMime || isManifestExt) {
    const ext = parsed.pathname.toLowerCase().endsWith('.mpd') || mime.includes('dash') ? 'mpd' : 'm3u8';
    return { kind: 'manifest', isManifest: true, ext, mimeType: mime || (ext === 'mpd' ? 'application/dash+xml' : 'application/vnd.apple.mpegurl') };
  }

  const isMediaMime = mime.startsWith('audio/') || mime === 'application/ogg' || mime === 'video/mp4' || mime === 'video/webm' || mime === 'video/quicktime';
  const isMediaExt = MEDIA_EXT_RE.test(parsed.pathname);
  const isGenericStreamMedia = (resourceType === 'media') && (!mime || mime === 'application/octet-stream' || mime === 'binary/octet-stream');

  if (!isMediaMime && !isMediaExt && !isGenericStreamMedia) return null;

  const ext = inferExtFromMime(mime, url);
  const kind = (mime.startsWith('video/') || ext === 'mp4' || ext === 'webm' || ext === 'mov') && !mime.startsWith('audio/') ? 'video' : 'audio';
  return {
    kind,
    isManifest: false,
    ext,
    mimeType: mime || (kind === 'video' ? `video/${ext}` : `audio/${ext === 'm4a' ? 'mp4' : ext === 'mp3' ? 'mpeg' : ext}`)
  };
}

function canonicalStreamKey(rawUrl) {
  try {
    const u = new URL(rawUrl);
    return `${u.origin}${u.pathname}`;
  } catch {
    return rawUrl;
  }
}

async function getTabStore() {
  const data = await chrome.storage.session.get('tabStreams');
  return data.tabStreams || {};
}

async function saveTabStore(store) {
  await chrome.storage.session.set({ tabStreams: store });
}

async function setTabBadge(tabId, list) {
  if (tabId < 0) return;
  try {
    const count = list.length;
    await chrome.action.setBadgeText({ tabId, text: count > 0 ? String(count) : '' });
    if (count > 0) {
      await chrome.action.setBadgeBackgroundColor({ tabId, color: '#06b6d4' });
    }
  } catch {}
}

async function recordStream(tabId, entry) {
  if (!Number.isInteger(tabId) || tabId < 0) return;
  const store = await getTabStore();
  const list = Array.isArray(store[tabId]) ? [...store[tabId]] : [];
  const key = canonicalStreamKey(entry.url);

  let pageTitle = entry.pageTitle || '';
  let pageUrl = entry.pageUrl || '';
  if (!pageTitle || !pageUrl) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab) {
        pageTitle = pageTitle || tab.title || '';
        pageUrl = pageUrl || tab.url || '';
      }
    } catch {}
  }

  const next = {
    url: entry.url,
    key,
    kind: entry.kind,
    isManifest: Boolean(entry.isManifest),
    ext: entry.ext,
    mimeType: entry.mimeType,
    contentLength: Number(entry.contentLength || 0),
    pageTitle,
    pageUrl,
    source: entry.source || 'network',
    detectedAt: Date.now()
  };

  const existingIdx = list.findIndex((item) => item.key === key || item.url === entry.url);
  if (existingIdx >= 0) {
    const prev = list[existingIdx];
    list[existingIdx] = {
      ...prev,
      ...next,
      contentLength: Math.max(Number(prev.contentLength || 0), Number(next.contentLength || 0))
    };
  } else {
    list.unshift(next);
  }

  store[tabId] = list.slice(0, MAX_STREAMS_PER_TAB);
  await saveTabStore(store);
  await setTabBadge(tabId, store[tabId]);
}

chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0) return;
    if (details.statusCode && details.statusCode >= 400) return;
    const hdrs = details.responseHeaders || [];
    let mime = '';
    let contentLength = 0;
    for (const h of hdrs) {
      const n = (h.name || '').toLowerCase();
      if (n === 'content-type') mime = h.value || '';
      if (n === 'content-length') contentLength = parseInt(h.value || '0', 10) || 0;
      if (n === 'content-range' && !contentLength) {
        const m = String(h.value || '').match(/\/(\d+)\s*$/);
        if (m) contentLength = parseInt(m[1], 10) || 0;
      }
    }
    const candidate = classifyMediaCandidate(details.url, mime, contentLength, details.type);
    if (!candidate) return;
    void recordStream(details.tabId, {
      url: details.url,
      pageUrl: details.initiator || details.documentUrl || '',
      contentLength,
      source: 'network',
      ...candidate
    });
  },
  { urls: ['http://*/*', 'https://*/*'], types: ['media', 'xmlhttprequest', 'other'] },
  ['responseHeaders']
);

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const store = await getTabStore();
  if (store[tabId]) {
    delete store[tabId];
    await saveTabStore(store);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (changeInfo.url && !changeInfo.url.startsWith('chrome://')) {
    const store = await getTabStore();
    if (store[tabId]) {
      delete store[tabId];
      await saveTabStore(store);
      await setTabBadge(tabId, []);
    }
  }
});

function bytesToBase64(uint8) {
  let binary = '';
  const step = 0x8000;
  for (let i = 0; i < uint8.length; i += step) {
    binary += String.fromCharCode.apply(null, uint8.subarray(i, i + step));
  }
  return btoa(binary);
}

function encodeHashGrab(payload) {
  const json = JSON.stringify(payload);
  const bytes = new TextEncoder().encode(json);
  return encodeURIComponent(bytesToBase64(bytes));
}

function pruneExpiredTransfers() {
  const cutoff = Date.now() - 180000;
  for (const [id, val] of pendingTransfers.entries()) {
    if (val.createdAt < cutoff) pendingTransfers.delete(id);
  }
}

async function openOrFocusStudioTab(targetBase, hashSuffix = '') {
  const normBase = String(targetBase || 'https://studio-5090403114-fc98b.web.app/').replace(/\/?$/, '/');
  const originPrefix = new URL(normBase).origin;
  const tabs = await chrome.tabs.query({});
  const existing = tabs.find((t) => t.url && t.url.startsWith(originPrefix));
  if (existing && !hashSuffix) {
    await chrome.tabs.update(existing.id, { active: true });
    return { tab: existing, reused: true };
  }
  const created = await chrome.tabs.create({ url: normBase + (hashSuffix ? `#${hashSuffix}` : ''), active: true });
  return { tab: created, reused: false };
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'ntk-soundlab-bridge') return;
  port.onMessage.addListener((msg) => {
    if (msg?.type !== 'REQUEST_TRANSFER' || !msg.transferId) return;
    pruneExpiredTransfers();
    const record = pendingTransfers.get(msg.transferId);
    if (!record) {
      port.postMessage({ type: 'TRANSFER_ERROR', transferId: msg.transferId, error: 'Transfer expired or missing.' });
      return;
    }
    const view = new Uint8Array(record.bytes);
    const totalChunks = Math.max(1, Math.ceil(view.length / CHUNK_BYTES));
    port.postMessage({
      type: 'TRANSFER_START',
      transferId: msg.transferId,
      totalBytes: view.length,
      totalChunks,
      meta: record.meta
    });
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_BYTES;
      const slice = view.subarray(start, Math.min(view.length, start + CHUNK_BYTES));
      port.postMessage({
        type: 'TRANSFER_CHUNK',
        transferId: msg.transferId,
        index: i,
        dataB64: bytesToBase64(slice)
      });
    }
    port.postMessage({ type: 'TRANSFER_DONE', transferId: msg.transferId });
    pendingTransfers.delete(msg.transferId);
  });
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || typeof msg !== 'object') return false;

  if (msg.type === 'GET_TAB_STREAMS') {
    (async () => {
      const store = await getTabStore();
      sendResponse({ ok: true, streams: store[msg.tabId] || [] });
    })();
    return true;
  }

  if (msg.type === 'CLEAR_TAB_STREAMS') {
    (async () => {
      const store = await getTabStore();
      delete store[msg.tabId];
      await saveTabStore(store);
      await setTabBadge(msg.tabId, []);
      sendResponse({ ok: true });
    })();
    return true;
  }

  if (msg.type === 'MERGE_DOM_STREAMS') {
    (async () => {
      for (const item of (msg.streams || [])) {
        const candidate = classifyMediaCandidate(item.url, item.mimeType, item.contentLength || 0, 'media');
        if (candidate) {
          await recordStream(msg.tabId, {
            url: item.url,
            pageTitle: msg.pageTitle || item.title || '',
            pageUrl: msg.pageUrl || '',
            source: item.source || 'dom',
            ...candidate
          });
        }
      }
      const store = await getTabStore();
      sendResponse({ ok: true, streams: store[msg.tabId] || [] });
    })();
    return true;
  }

  if (msg.type === 'DOWNLOAD_STREAM') {
    (async () => {
      try {
        const fileName = sanitizeFileName(msg.title || 'SoundLab_Capture', msg.ext || 'mp3');
        const downloadId = await chrome.downloads.download({
          url: msg.url,
          filename: fileName,
          saveAs: true
        });
        sendResponse({ ok: true, downloadId });
      } catch (err) {
        sendResponse({ ok: false, error: err?.message || 'Chrome download failed.' });
      }
    })();
    return true;
  }

  if (msg.type === 'SEND_TO_SOUNDLAB') {
    (async () => {
      const { item, targetUrl, pageMeta } = msg;
      const title = (pageMeta?.title || item.pageTitle || 'Captured Media').trim();
      const artist = (pageMeta?.artist || '').trim();
      const coverUrl = (pageMeta?.coverUrl || '').trim();
      const sourceUrl = (pageMeta?.pageUrl || item.pageUrl || item.url).trim();
      const fileName = sanitizeFileName(title, item.ext || 'mp3');

      if (item.isManifest) {
        const grabHash = `grab=${encodeHashGrab({ url: item.url, title, artist, cover: coverUrl, ext: item.ext, pageUrl: sourceUrl })}`;
        await openOrFocusStudioTab(targetUrl, grabHash);
        sendResponse({ ok: true, method: 'url-hash' });
        return;
      }

      try {
        const resp = await fetch(item.url, { credentials: 'include' });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const respMime = String(resp.headers.get('content-type') || item.mimeType || '').split(';')[0].trim().toLowerCase();
        if (respMime.startsWith('text/html') || respMime === 'application/json') {
          throw new Error(`Unexpected response type: ${respMime}`);
        }
        const lenHdr = parseInt(resp.headers.get('content-length') || '0', 10) || 0;
        if (lenHdr > MAX_TRANSFER_BYTES) throw new Error('File exceeds 150 MB direct transfer limit.');

        const ab = await resp.arrayBuffer();
        if (ab.byteLength === 0 || ab.byteLength > MAX_TRANSFER_BYTES) {
          throw new Error(ab.byteLength === 0 ? 'Empty media response.' : 'File exceeds 150 MB direct transfer limit.');
        }

        const ext = inferExtFromMime(respMime, item.url);
        const safeMime = respMime || (item.kind === 'video' ? `video/${ext}` : `audio/${ext === 'm4a' ? 'mp4' : ext === 'mp3' ? 'mpeg' : ext}`);
        const transferId = crypto.randomUUID();
        pruneExpiredTransfers();
        pendingTransfers.set(transferId, {
          bytes: ab,
          createdAt: Date.now(),
          meta: {
            fileName: sanitizeFileName(title, ext),
            mimeType: safeMime,
            title,
            artist: artist || 'Browser Grabber',
            coverUrl,
            sourceUrl,
            streamUrl: item.url
          }
        });

        const normBase = String(targetUrl || 'https://studio-5090403114-fc98b.web.app/').replace(/\/?$/, '/');
        const originPrefix = new URL(normBase).origin;
        const tabs = await chrome.tabs.query({});
        const existing = tabs.find((t) => t.url && t.url.startsWith(originPrefix));
        if (existing) {
          await chrome.tabs.update(existing.id, { active: true });
          try {
            await chrome.tabs.sendMessage(existing.id, { type: 'TRANSFER_AVAILABLE', transferId });
            sendResponse({ ok: true, method: 'bridge-existing' });
            return;
          } catch {}
        }

        await chrome.tabs.create({ url: `${normBase}#ext-transfer=${encodeURIComponent(transferId)}`, active: true });
        sendResponse({ ok: true, method: 'bridge-new-tab' });
      } catch (err) {
        const grabHash = `grab=${encodeHashGrab({ url: item.url, title, artist, cover: coverUrl, ext: item.ext, pageUrl: sourceUrl })}`;
        await openOrFocusStudioTab(targetUrl, grabHash);
        sendResponse({ ok: true, method: 'url-fallback', warning: err?.message || 'Fell back to URL handoff.' });
      }
    })();
    return true;
  }

  return false;
});
