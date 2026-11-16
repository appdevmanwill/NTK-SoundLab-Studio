import { safeFilename } from './media-utils.mjs';
import { waitForDownload } from './download-utils.mjs';

const api = globalThis.browser || globalThis.chrome;
const ui = Object.fromEntries(['name', 'silent', 'choose', 'record', 'stop', 'save', 'preview', 'details', 'status'].map(id => [id, document.getElementById(id)]));
const MAX_BYTES = 2 * 1024 ** 3;
let stream, recorder, directory, handle, writer, temporaryName, savedFile, objectUrl;
let state = 'idle', bytes = 0, started = 0, timer, countdown, writes = Promise.resolve(), writeError, endingNote = '';

function status(message, error = false) {
  ui.status.textContent = message;
  ui.status.className = error ? 'error' : '';
}

function setState(next) {
  state = next;
  ui.choose.disabled = !['idle', 'ready', 'saved', 'error'].includes(state);
  ui.record.disabled = state !== 'ready';
  ui.stop.disabled = !['ready', 'countdown', 'recording'].includes(state);
  ui.stop.textContent = state === 'recording' ? 'Stop & save' : 'Cancel selection';
  ui.save.hidden = !savedFile;
  ui.save.disabled = !['saved', 'error'].includes(state);
  ui.silent.disabled = !['idle', 'saved', 'error'].includes(state);
}

function releaseCapture() {
  clearInterval(timer); clearInterval(countdown);
  for (const track of stream?.getTracks() || []) track.stop();
  stream = null;
  ui.preview.srcObject = null;
  ui.preview.hidden = true;
}

async function cleanFile() {
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null; savedFile = null;
  if (directory && temporaryName) await directory.removeEntry(temporaryName).catch(() => {});
  temporaryName = null;
}

async function choose() {
  setState('selecting');
  status('Choose the playing tab and enable Share tab audio.');
  releaseCapture();
  try {
    // This call must remain in the click handler before any await so browsers retain user activation.
    const pending = navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: 'browser', frameRate: { ideal: 30, max: 60 } },
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, suppressLocalAudioPlayback: false },
      selfBrowserSurface: 'exclude', surfaceSwitching: 'exclude', systemAudio: 'exclude', monitorTypeSurfaces: 'exclude',
    });
    stream = await pending;
    if (!stream.getAudioTracks().length && !ui.silent.checked) {
      throw new Error('No audio was shared. Select the source browser tab and enable Share tab audio. Firefox may not offer this; use Chrome, Edge or Opera for sound.');
    }
    await cleanFile();
    const settings = stream.getVideoTracks()[0].getSettings();
    ui.details.textContent = `${settings.width || '?'} × ${settings.height || '?'} capture · ${stream.getAudioTracks().length ? 'Sound included' : 'Silent recording'}`;
    stream.getVideoTracks()[0].addEventListener('ended', stop, { once: true });
    ui.preview.srcObject = stream; ui.preview.hidden = false;
    setState('ready');
    status('Capture selected. Start recording when you are ready.');
  } catch (error) {
    releaseCapture(); setState('error');
    status(error.name === 'NotAllowedError' ? 'Selection cancelled or blocked. Choose a tab to try again.' : error.message, true);
  }
}

function recorderType(hasAudio) {
  const candidates = hasAudio
    ? ['video/mp4;codecs=avc1.42001E,mp4a.40.2', 'video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus']
    : ['video/mp4;codecs=avc1.42001E', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8'];
  return candidates.find(type => MediaRecorder.isTypeSupported(type)) || '';
}

async function begin() {
  setState('preparing');
  try {
    const root = await navigator.storage.getDirectory();
    directory = await root.getDirectoryHandle('soundlab-recordings', { create: true });
    temporaryName = crypto.randomUUID();
    handle = await directory.getFileHandle(temporaryName, { create: true });
    writer = await handle.createWritable();
    if (stream?.getVideoTracks()[0]?.readyState !== 'live') throw new Error('Tab sharing ended. Select the playing tab again.');
    recorder = new MediaRecorder(stream, {
      mimeType: recorderType(stream.getAudioTracks().length > 0),
      videoBitsPerSecond: 12_000_000, audioBitsPerSecond: 320_000,
    });
    bytes = 0; writeError = null; endingNote = ''; writes = Promise.resolve();
    recorder.addEventListener('dataavailable', event => {
      if (!event.data.size) return;
      bytes += event.data.size;
      writes = writes.then(() => writer.write(event.data)).catch(error => {
        writeError = error; if (recorder.state !== 'inactive') recorder.stop();
      });
      if (bytes >= MAX_BYTES && recorder.state !== 'inactive') { endingNote = 'The 2 GB recording limit was reached. '; stop(); }
    });
    recorder.addEventListener('error', event => { writeError = event.error || new Error('Recording failed.'); stop(); });
    recorder.addEventListener('stop', finish, { once: true });
    setState('countdown');
    let remaining = 5;
    status(`Recording starts in ${remaining} seconds. Return to the source tab.`);
    countdown = setInterval(() => {
      remaining -= 1;
      if (remaining > 0) { status(`Recording starts in ${remaining} seconds. Return to the source tab.`); return; }
      clearInterval(countdown);
      try {
        recorder.start(1000); started = Date.now(); setState('recording');
        status('Recording picture and sound. Return here to stop and save.');
        timer = setInterval(() => {
          const seconds = Math.floor((Date.now() - started) / 1000);
          status(`Recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} · ${(bytes / 1024 ** 2).toFixed(1)} MB. Return here to stop and save.`);
          if (seconds >= 3600) { endingNote = 'The one-hour recording limit was reached. '; stop(); }
        }, 1000);
      } catch (error) { void fail(error); }
    }, 1000);
  } catch (error) { await fail(error); }
}

async function fail(error) {
  releaseCapture();
  if (writer) await writer.abort().catch(() => {});
  writer = null; await cleanFile(); setState('error'); status(error.message || 'Recording failed.', true);
}

function stop() {
  if (state === 'recording') {
    setState('saving'); clearInterval(timer);
    if (recorder.state !== 'inactive') recorder.stop();
  } else if (['ready', 'countdown'].includes(state)) {
    releaseCapture(); setState('idle'); status('Selection cancelled.');
    if (writer) void writer.abort().catch(() => {}).then(() => { writer = null; return cleanFile(); });
  }
}

async function finish() {
  releaseCapture(); setState('saving'); status('Preparing the recording…');
  await writes;
  if (writeError) { await fail(writeError); return; }
  try {
    await writer.close(); writer = null;
    savedFile = await handle.getFile();
    if (!savedFile.size) throw new Error('The recording is empty. Select the source and try again.');
    await save();
  } catch (error) { if (savedFile) { setState('error'); status(error.message, true); } else await fail(error); }
}

async function save() {
  setState('saving'); status('Choose where to save your recording.');
  try {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(savedFile);
    const ext = recorder.mimeType.includes('mp4') ? 'mp4' : 'webm';
    const id = await api.downloads.download({ url: objectUrl, filename: safeFilename(ui.name.value || 'SoundLab playback', ext), saveAs: true });
    await waitForDownload(id);
    status(endingNote + 'Saved. Your recording is available in the browser’s downloads.'); setState('saved');
  } catch (error) {
    setState('error'); status(`${error.message} Your recording is still here. Choose Save recording again.`, true);
  }
}

ui.choose.addEventListener('click', choose);
ui.record.addEventListener('click', begin);
ui.stop.addEventListener('click', stop);
ui.save.addEventListener('click', save);
window.addEventListener('beforeunload', event => {
  if (!['idle', 'saved'].includes(state)) { event.preventDefault(); event.returnValue = ''; }
});
window.addEventListener('pagehide', () => { releaseCapture(); void cleanFile(); });
