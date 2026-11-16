const statusEl = document.getElementById('statusLine');
const listEl = document.getElementById('streamsList');
const titleEl = document.getElementById('pageTitle');
const targetSelect = document.getElementById('studioTarget');
const clearBtn = document.getElementById('btnClear');

let activeTab = null;
let activeMeta = { title: '', artist: '', coverUrl: '', pageUrl: '' };

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return 'Stream';
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function setStatus(msg, isError = false) {
  statusEl.style.color = isError ? '#fda4af' : '#6ee7b7';
  statusEl.textContent = msg;
}

async function scanActiveTabDom(tabId) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const metaContent = (sel) => document.querySelector(sel)?.getAttribute('content') || '';
        const title = (metaContent('meta[property="og:title"]') || document.title || '').replace(/\s*[|-]\s*(Audiomack|SoundCloud|Suno|YouTube|Vimeo).*$/i, '').trim();
        const artist = (metaContent('meta[name="author"]') || metaContent('meta[property="music:musician"]') || '').trim();
        const coverUrl = metaContent('meta[property="og:image"]') || metaContent('meta[name="twitter:image"]') || '';
        const streams = [];
        const add = (url, mimeType, source) => {
          if (url && /^https?:\/\//i.test(url)) streams.push({ url, mimeType: mimeType || '', source });
        };

        document.querySelectorAll('audio, video').forEach((el) => {
          add(el.currentSrc || el.src, '', 'dom');
          el.querySelectorAll('source').forEach((s) => add(s.src, s.type || '', 'dom'));
        });
        add(metaContent('meta[property="og:audio"]'), 'audio/mpeg', 'og');
        add(metaContent('meta[property="og:video"]'), 'video/mp4', 'og');

        for (const entry of performance.getEntriesByType('resource')) {
          if (/\.(mp3|m4a|aac|wav|flac|ogg|opus|webm|mp4|m3u8|mpd)(?:$|[?#])/i.test(entry.name)) {
            add(entry.name, '', 'perf');
          }
        }
        return { title, artist, coverUrl, pageUrl: location.href, streams };
      }
    });
    return result || { streams: [] };
  } catch {
    return { streams: [] };
  }
}

function renderStreams(streams) {
  listEl.textContent = '';
  const ordered = [...streams].sort((a, b) => {
    const rank = (k) => (k === 'audio' ? 0 : k === 'video' ? 1 : 2);
    return rank(a.kind) - rank(b.kind) || b.detectedAt - a.detectedAt;
  });

  if (ordered.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.innerHTML = 'No audio or video stream captured on this tab yet.<br><br><strong>Press Play</strong> on the page player (Audiomack, ACE Music, etc.) and reopen this popup — Chrome will list every unencrypted media stream here automatically.';
    listEl.appendChild(empty);
    return;
  }

  for (const item of ordered) {
    const card = document.createElement('div');
    card.className = 'item';

    const top = document.createElement('div');
    top.className = 'item-top';

    const badge = document.createElement('span');
    badge.className = `badge ${item.kind === 'video' ? 'badge-video' : item.isManifest ? 'badge-manifest' : 'badge-audio'}`;
    badge.textContent = `${item.kind === 'manifest' ? 'HLS/DASH' : item.kind} • ${(item.ext || 'BIN').toUpperCase()}`;

    const size = document.createElement('span');
    size.style.cssText = 'font-size:11px;color:#cbd5e1;font-weight:600';
    size.textContent = formatBytes(item.contentLength);

    top.append(badge, size);

    const urlLine = document.createElement('div');
    urlLine.className = 'url-line';
    urlLine.title = item.url;
    urlLine.textContent = item.url;

    const actions = document.createElement('div');
    actions.className = 'actions';

    const sendBtn = document.createElement('button');
    sendBtn.className = 'btn btn-primary';
    sendBtn.textContent = item.isManifest ? '⚡ Send Manifest URL' : '⚡ Send to SoundLab';
    sendBtn.onclick = async () => {
      sendBtn.disabled = true;
      setStatus(item.isManifest ? 'Sending playlist URL to SoundLab...' : 'Fetching media stream & importing to SoundLab...');
      const res = await chrome.runtime.sendMessage({
        type: 'SEND_TO_SOUNDLAB',
        item,
        targetUrl: targetSelect.value,
        pageMeta: activeMeta
      });
      sendBtn.disabled = false;
      if (res?.ok) {
        setStatus(res.warning ? `Opened Studio URL fallback (${res.warning})` : 'Imported into NTK SoundLab Studio!');
      } else {
        setStatus(res?.error || 'Could not import stream.', true);
      }
    };

    const dlBtn = document.createElement('button');
    dlBtn.className = 'btn';
    dlBtn.textContent = '⬇ Save';
    dlBtn.onclick = async () => {
      setStatus('Starting Chrome download...');
      const res = await chrome.runtime.sendMessage({
        type: 'DOWNLOAD_STREAM',
        url: item.url,
        ext: item.ext,
        title: activeMeta.title || item.pageTitle
      });
      setStatus(res?.ok ? 'Download started!' : (res?.error || 'Download failed.'), !res?.ok);
    };

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn';
    copyBtn.textContent = '📋 Copy';
    copyBtn.onclick = async () => {
      await navigator.clipboard.writeText(item.url);
      setStatus('Copied stream URL to clipboard.');
    };

    actions.append(sendBtn, dlBtn, copyBtn);
    card.append(top, urlLine, actions);
    listEl.appendChild(card);
  }
}

async function init() {
  const saved = await chrome.storage.local.get('studioTarget');
  if (saved.studioTarget) targetSelect.value = saved.studioTarget;
  targetSelect.addEventListener('change', () => {
    chrome.storage.local.set({ studioTarget: targetSelect.value });
  });

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  activeTab = tab;
  if (!tab || !tab.id) {
    titleEl.textContent = 'No active tab';
    renderStreams([]);
    return;
  }

  titleEl.textContent = tab.title || tab.url || 'Current Tab';
  const domData = await scanActiveTabDom(tab.id);
  activeMeta = {
    title: domData.title || tab.title || 'Captured Media',
    artist: domData.artist || '',
    coverUrl: domData.coverUrl || '',
    pageUrl: domData.pageUrl || tab.url || ''
  };

  if (domData.streams && domData.streams.length > 0) {
    const merged = await chrome.runtime.sendMessage({
      type: 'MERGE_DOM_STREAMS',
      tabId: tab.id,
      pageTitle: activeMeta.title,
      pageUrl: activeMeta.pageUrl,
      streams: domData.streams
    });
    renderStreams(merged?.streams || []);
  } else {
    const resp = await chrome.runtime.sendMessage({ type: 'GET_TAB_STREAMS', tabId: tab.id });
    renderStreams(resp?.streams || []);
  }

  clearBtn.onclick = async () => {
    await chrome.runtime.sendMessage({ type: 'CLEAR_TAB_STREAMS', tabId: tab.id });
    renderStreams([]);
    setStatus('Cleared captured streams for this tab.');
  };
}

void init();
