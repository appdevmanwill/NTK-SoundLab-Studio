import { qualityLabel } from './media-utils.mjs';
const browserApi = globalThis.browser || globalThis.chrome;
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
    const frames = await browserApi.scripting.executeScript({
      target: { tabId, allFrames: true },
      func: () => {
        const metaContent = (sel) => document.querySelector(sel)?.getAttribute('content') || '';
        const title = (metaContent('meta[property="og:title"]') || document.title || '').replace(/\s*[|-]\s*(Audiomack|SoundCloud|Suno|YouTube|Vimeo).*$/i, '').trim();
        const artist = (metaContent('meta[name="author"]') || metaContent('meta[property="music:musician"]') || '').trim();
        const coverUrl = metaContent('meta[property="og:image"]') || metaContent('meta[name="twitter:image"]') || '';
        const streams = [];
        const add = (url, mimeType, source, extra = {}) => {
          if (url && /^https?:\/\//i.test(url)) streams.push({ url, mimeType: mimeType || '', source, ...extra });
        };

        document.querySelectorAll('audio, video').forEach((el) => {
          add(el.currentSrc || el.src, el.querySelector('source')?.type || (el.tagName === 'VIDEO' ? 'video/unknown' : 'audio/unknown'), 'dom', { width: el.videoWidth || 0, height: el.videoHeight || 0 });
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
    const main = frames.find(frame => frame.frameId === 0)?.result || {};
    return { ...main, streams: frames.flatMap(frame => frame.result?.streams || []) };
  } catch {
    return { streams: [] };
  }
}

function renderStreams(streams) {
  listEl.textContent = '';
  const ordered = [...streams].sort((a, b) => {
    const rank = (k) => (k === 'video' ? 0 : k === 'manifest' ? 1 : 2);
    return Number(a.isSegment) - Number(b.isSegment) || rank(a.kind) - rank(b.kind) || (b.width || 0) * (b.height || 0) - (a.width || 0) * (a.height || 0) || b.detectedAt - a.detectedAt;
  });

  if (ordered.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.innerHTML = 'No complete media stream captured yet.<br><br><strong>Press Play</strong> and reopen the grabber. For a storyboard or animated page, use Record playback.';
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
    size.textContent = [qualityLabel(item), formatBytes(item.contentLength)].join(' · ');

    top.append(badge, size);

    const urlLine = document.createElement('div');
    urlLine.className = 'url-line';
    urlLine.title = item.url;
    try { const url = new URL(item.url); urlLine.textContent = url.hostname + url.pathname; } catch { urlLine.textContent = 'Captured stream'; }

    const actions = document.createElement('div');
    actions.className = 'actions';

    const sendBtn = document.createElement('button');
    sendBtn.className = 'btn btn-primary';
    sendBtn.textContent = item.kind === 'video' ? 'Edit audio in SoundLab' : 'Send to SoundLab';
    sendBtn.disabled = Boolean(item.isManifest || item.isSegment);
    if (sendBtn.disabled) sendBtn.title = 'Save the complete stream first, then import the file into SoundLab.';
    sendBtn.onclick = async () => {
      sendBtn.disabled = true;
      setStatus(item.isManifest ? 'Sending playlist URL to SoundLab...' : 'Fetching media stream & importing to SoundLab...');
      const res = await browserApi.runtime.sendMessage({
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

    const formats = [
      ['original', item.isManifest ? 'Save stream' : 'Original'],
      ['mp3', 'MP3 320k'],
      ['wav', 'WAV 24-bit'],
      ['studio', 'Trim or split audio'],
    ];
    if (item.kind === 'video' || item.isManifest) formats.unshift(['video', 'Save video']);
    const downloadButtons = formats.map(([format, label]) => {
      const button = document.createElement('button');
      button.className = 'btn';
      button.textContent = label;
      button.disabled = Boolean(item.isSegment || (format === 'studio' && item.ext === 'mpd'));
      button.onclick = async () => {
        try {
          const result = await browserApi.runtime.sendMessage({
            type: 'OPEN_EXPORT', tabId: activeTab.id, url: item.url,
            title: activeMeta.title || item.pageTitle, format,
          });
          setStatus(result?.ok ? 'Opened the download page.' : result?.error || 'Could not open export.', !result?.ok);
        } catch (error) { setStatus(error.message, true); }
      };
      return button;
    });

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn';
    copyBtn.textContent = '📋 Copy';
    copyBtn.onclick = async () => {
      await navigator.clipboard.writeText(item.url);
      setStatus('Copied stream URL to clipboard.');
    };

    actions.append(...downloadButtons, sendBtn, copyBtn);
    card.append(top, urlLine, actions);
    listEl.appendChild(card);
  }
}

const recordButton = document.getElementById('btnRecord');
if (!navigator.mediaDevices?.getDisplayMedia || /Android/i.test(navigator.userAgent)) {
  recordButton.disabled = true;
  recordButton.nextElementSibling.textContent = 'Playback recording is available on supported desktop browsers. File downloads and the audio studio are separate tools.';
}
recordButton.addEventListener('click', async () => {
  await browserApi.tabs.create({ url: browserApi.runtime.getURL('record.html') });
});

document.getElementById('btnStudio').addEventListener('click', async () => {
  try {
    await browserApi.tabs.create({ url: browserApi.runtime.getURL('studio.html') });
  } catch (error) { setStatus(error.message, true); }
});

async function init() {
  const saved = await browserApi.storage.local.get('studioTarget');
  if (saved.studioTarget) targetSelect.value = saved.studioTarget;
  targetSelect.addEventListener('change', () => {
    browserApi.storage.local.set({ studioTarget: targetSelect.value });
  });

  const [tab] = await browserApi.tabs.query({ active: true, currentWindow: true });
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
    const merged = await browserApi.runtime.sendMessage({
      type: 'MERGE_DOM_STREAMS',
      tabId: tab.id,
      pageTitle: activeMeta.title,
      pageUrl: activeMeta.pageUrl,
      streams: domData.streams
    });
    renderStreams(merged?.streams || []);
  } else {
    const resp = await browserApi.runtime.sendMessage({ type: 'GET_TAB_STREAMS', tabId: tab.id });
    renderStreams(resp?.streams || []);
  }

  clearBtn.onclick = async () => {
    await browserApi.runtime.sendMessage({ type: 'CLEAR_TAB_STREAMS', tabId: tab.id });
    renderStreams([]);
    setStatus('Cleared captured streams for this tab.');
  };
}

void init().catch(error => setStatus(error.message || 'Could not read this tab.', true));
