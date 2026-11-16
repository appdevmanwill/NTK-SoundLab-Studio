import { inspectMedia, writeMedia } from './media-export.mjs';
import { mediaUrl, safeFilename } from './media-utils.mjs';
import { waitForDownload } from './download-utils.mjs';

const api = globalThis.browser || globalThis.chrome;
const elements = Object.fromEntries(['title', 'source', 'format', 'start', 'cancel', 'progress', 'status', 'details'].map(id => [id, document.getElementById(id)]));
const jobId = location.hash.slice(1);
let job, controller, downloadId, objectUrl, directory, temporaryName;
let running = false;

function status(message, error = false) {
  elements.status.textContent = message;
  elements.status.className = error ? 'error' : '';
}

function progress(percent) {
  if (percent === null) elements.progress.removeAttribute('value');
  else elements.progress.value = percent;
}

async function cleanTemporary() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
  if (directory && temporaryName) await directory.removeEntry(temporaryName).catch(() => {});
  temporaryName = null;
}

async function start() {
  running = true;
  elements.start.disabled = true;
  elements.format.disabled = true;
  elements.cancel.disabled = false;
  elements.details.textContent = '';
  controller = new AbortController();
  let media, writer;
  downloadId = null;
  try {
    const format = elements.format.value;
    const source = mediaUrl(job.item.url);
    if (format === 'original' && !job.item.isManifest) {
      status('Choose where to save the original file.');
      downloadId = await api.downloads.download({ url: source, filename: safeFilename(job.title, job.item.ext || 'bin'), saveAs: true });
    } else {
      if (job.item.ext === 'mpd') throw new Error('DASH manifests need an additional downloader. Capture a complete MP4/WebM file or an HLS playlist instead.');
      status('Reading available audio and video tracks…');
      progress(null);
      media = await inspectMedia(source, controller.signal);
      const { width, height, sampleRate, channels } = media.details;
      elements.details.textContent = [width ? `${width} × ${height} video` : '', sampleRate ? `${sampleRate.toLocaleString()} Hz · ${channels} audio channel(s)` : ''].filter(Boolean).join(' · ');
      const selected = format === 'original' ? (media.video ? 'video' : 'wav') : format;
      const extension = selected === 'video' ? 'mp4' : selected;
      const root = await navigator.storage.getDirectory();
      directory = await root.getDirectoryHandle('soundlab-exports', { create: true });
      temporaryName = crypto.randomUUID();
      const handle = await directory.getFileHandle(temporaryName, { create: true });
      writer = await handle.createWritable();
      status(selected === 'video' ? 'Saving video at source quality…' : selected === 'mp3' ? 'Encoding MP3 at 320 kbps…' : 'Writing 24-bit WAV audio…');
      await writeMedia(media, selected, writer, controller.signal, value => progress(value === null ? null : value <= 1 && selected !== 'mp3' ? value * 100 : value));
      controller.signal.throwIfAborted();
      await writer.close(); writer = null;
      const file = await handle.getFile();
      if (!file.size) throw new Error('The export is empty. Replay the source and capture it again.');
      objectUrl = URL.createObjectURL(file);
      status('Choose where to save your finished file.');
      downloadId = await api.downloads.download({ url: objectUrl, filename: safeFilename(job.title, extension), saveAs: true });
    }
    if (controller.signal.aborted && downloadId !== null) {
      await api.downloads.cancel(downloadId).catch(() => {});
    }
    controller.signal.throwIfAborted();
    status('Saving file…');
    await waitForDownload(downloadId);
    progress(100);
    status('Saved. Your file is available in the browser’s downloads.');
  } catch (error) {
    status(controller.signal.aborted ? 'Cancelled. You can start again.' : error.message || 'Export failed.', !controller.signal.aborted);
    if (writer) await writer.abort().catch(() => {});
  } finally {
    media?.input.dispose();
    await cleanTemporary();
    running = false;
    elements.start.disabled = false;
    elements.format.disabled = false;
    elements.cancel.disabled = true;
  }
}

elements.start.addEventListener('click', start);
elements.cancel.addEventListener('click', () => {
  controller?.abort();
  if (downloadId !== null) void api.downloads.cancel(downloadId).catch(() => {});
});
window.addEventListener('beforeunload', event => {
  if (running) { event.preventDefault(); event.returnValue = ''; }
});

try {
  const oldJobs = await api.storage.session.get(null);
  const expired = Object.entries(oldJobs).filter(([key, value]) => key.startsWith('export-') && value.createdAt && Date.now() - value.createdAt > 86400000).map(([key]) => key);
  if (expired.length) await api.storage.session.remove(expired);
  const data = await api.storage.session.get(jobId);
  job = data[jobId];
  if (!job?.item?.url) throw new Error('This capture has expired. Play the media and open the grabber again.');
  mediaUrl(job.item.url);
  elements.title.textContent = job.title || 'Captured media';
  elements.source.textContent = new URL(job.item.url).hostname;
  elements.format.value = job.format || 'original';
  elements.start.disabled = false;
  status('Ready to save.');
} catch (error) { status(error.message, true); }
