import { AudioBufferSink } from './lib/mediabunny.js';
import { inspectMedia } from './media-export.mjs';
import { safeFilename } from './media-utils.mjs';
import { waitForDownload } from './download-utils.mjs';
import { AudioConverter } from './js/audio-converter.js?v=2026.11.16.3';
import { AudioFXEngine } from './js/audio-fx.js?v=2026.11.16.3';
import { ID3Writer } from './js/id3-writer.js?v=2026.11.16.3';
import { Mp3Encoder } from './js/mp3-encoder.js?v=2026.11.16.3';
import { StemEngine } from './js/stem-engine.js?v=2026.11.16.3';
import { StemMixer } from './js/stem-mixer.js?v=2026.11.16.3';
import { MODEL, importOfflineModel } from './js/offline-model.js?v=2026.11.16.3';

const api = globalThis.browser || globalThis.chrome;
const ui = Object.fromEntries([...document.querySelectorAll('[id]')].map(element => [element.id, element]));
const MAX_SECONDS = 120;
const MAX_FILE_BYTES = 150 * 1024 ** 2;
const TRACK_NAMES = { vocals: 'Vocals', instrumental: 'Instrumental', drums: 'Drums', bass: 'Bass', other: 'Other' };
const mixer = new StemMixer(() => {
  ui.mixPlay.textContent = mixer.isPlaying ? 'Pause mix' : 'Play mix';
});
let source, job, operation, previewUrl, fileTitle;
let waveform = [];

function status(message, error = false) {
  ui.status.textContent = message;
  ui.status.className = error ? 'error' : '';
}

function controls() {
  ui.file.disabled = ui.capture.disabled = ui.model.disabled = ui.stemMode.disabled = Boolean(operation);
  ui.editor.disabled = !source || Boolean(operation);
  ui.split.disabled = !source || Boolean(operation);
  for (const control of ui.mix.querySelectorAll('button, input')) control.disabled = Boolean(operation);
}

async function run(action, { cancellable = false } = {}) {
  if (operation) return;
  const controller = new AbortController();
  operation = controller;
  controls();
  ui.cancel.hidden = !cancellable;
  ui.cancel.disabled = false;
  ui.progress.hidden = false;
  ui.progress.removeAttribute('value');
  try {
    await action(controller.signal);
  } catch (error) {
    status(controller.signal.aborted ? 'Cancelled.' : error.message, !controller.signal.aborted);
  } finally {
    operation = null;
    ui.cancel.hidden = ui.progress.hidden = true;
    controls();
  }
}

function stopPreview() {
  ui.player.pause();
  ui.player.removeAttribute('src');
  ui.player.load();
  ui.player.hidden = true;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
}

function renderWaveform() {
  const { width, height } = ui.wave;
  const ctx = ui.wave.getContext('2d');
  ctx.clearRect(0, 0, width, height);
  if (!source) return;
  const start = Number(ui.from.value) / source.duration * width;
  const end = Number(ui.to.value) / source.duration * width;
  ctx.fillStyle = '#244255';
  ctx.fillRect(start, 0, Math.max(0, end - start), height);
  ctx.fillStyle = '#67e8f9';
  waveform.forEach((peak, index) => {
    const bar = Math.max(1, Math.min(height, peak * height));
    ctx.fillRect(index * 2, (height - bar) / 2, 1, bar);
  });
}

function loadSource(input, title) {
  return run(async signal => {
    status('Reading audio…');
    if (input instanceof Blob && input.size > MAX_FILE_BYTES) throw new Error('Choose a file under 150 MB.');
    const media = await inspectMedia(input, signal);
    try {
      if (!media.audio || !await media.audio.canDecode()) throw new Error('This browser cannot decode an audio track from this source.');
      if (media.details.duration > MAX_SECONDS + 0.001) throw new Error('Choose a clip no longer than 2 minutes. For longer recordings, use the full SoundLab app.');
      const { sampleRate, channels } = media.details;
      if (channels < 1 || channels > 2 || !Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 96000) {
        throw new Error('Choose mono or stereo audio between 8 and 96 kHz.');
      }
      const buffers = [];
      let frames = 0;
      for await (const { buffer } of new AudioBufferSink(media.audio).buffers()) {
        signal.throwIfAborted();
        frames += buffer.length;
        if (frames > MAX_SECONDS * sampleRate) throw new Error('The decoded audio exceeds 2 minutes.');
        buffers.push(buffer);
      }
      if (frames < sampleRate / 10) throw new Error('Choose at least 0.1 seconds of audio.');
      const decoded = new AudioBuffer({ length: frames, numberOfChannels: channels, sampleRate });
      let offset = 0;
      for (const buffer of buffers) {
        for (let channel = 0; channel < channels; channel++) decoded.copyToChannel(buffer.getChannelData(channel), channel, offset);
        offset += buffer.length;
      }
      stopPreview();
      mixer.stop();
      mixer.stems = null;
      ui.mix.hidden = true;
      source = decoded;
      fileTitle = safeFilename(title, 'wav').slice(0, -4);
      ui.title.value = fileTitle;
      ui.artist.value = ui.album.value = ui.cover.value = '';
      ui.loadedFile.textContent = `${fileTitle} · ${source.duration.toFixed(2)} seconds`;
      ui.loadedFile.hidden = false;
      ui.from.value = 0;
      ui.to.value = source.duration;
      ui.from.max = ui.to.max = source.duration;
      waveform = AudioConverter.computePeaks(source, ui.wave.width / 2);
      renderWaveform();
      status(`Loaded ${fileTitle} · ${source.duration.toFixed(2)} seconds`);
    } finally {
      media.input.dispose();
    }
  }, { cancellable: true });
}

function selection() {
  const startSec = ui.from.valueAsNumber;
  const endSec = ui.to.valueAsNumber;
  if (![startSec, endSec].every(Number.isFinite) || startSec < 0 || endSec > source.duration || endSec - startSec < 0.099999) {
    throw new Error('Set a valid selection at least 0.1 seconds long.');
  }
  return AudioFXEngine.process(source, {
    startSec, endSec, fadeInSec: ui.fadeIn.valueAsNumber, fadeOutSec: ui.fadeOut.valueAsNumber,
    normalize: ui.normalize.checked, preset: ui.preset.value,
  });
}

async function save(blob, title, format) {
  const url = URL.createObjectURL(blob);
  try {
    const id = await api.downloads.download({ url, filename: safeFilename(title, format), saveAs: true });
    await waitForDownload(id);
    status('Saved to your downloads.');
  } finally {
    URL.revokeObjectURL(url);
  }
}

function exportSelection(format) {
  return run(async () => {
    status('Preparing the selection…');
    const cover = ui.cover.files[0];
    if (format === 'mp3' && cover && (cover.size > 4 * 1024 ** 2 || !['image/jpeg', 'image/png'].includes(cover.type))) {
      throw new Error('Use a JPEG or PNG cover under 4 MB.');
    }
    const audio = await selection();
    const title = ui.title.value.trim() || fileTitle;
    if (format === 'wav') {
      await save(AudioConverter.encodeWav(audio), title, format);
      return;
    }
    const blob = await Mp3Encoder.encode(audio, 320, percent => { ui.progress.value = percent; });
    const tagged = await ID3Writer.embedTags(blob, {
      title, artist: ui.artist.value.trim() || 'Unknown artist',
      album: ui.album.value.trim() || 'SoundLab Studio', genre: 'Other',
      coverBytes: cover ? new Uint8Array(await cover.arrayBuffer()) : undefined,
      coverMime: cover?.type,
    });
    await save(tagged, title, format);
  });
}

function renderMixer() {
  ui.tracks.replaceChildren();
  for (const track of mixer.getActiveTrackKeys()) {
    const name = TRACK_NAMES[track];
    const row = document.createElement('div');
    row.className = 'track';
    const label = document.createElement('strong');
    label.textContent = name;
    const volume = document.createElement('input');
    Object.assign(volume, { type: 'range', min: '0', max: '1.5', step: '0.01', value: mixer.state[track].volume });
    volume.setAttribute('aria-label', `${name} volume`);
    volume.oninput = () => mixer.setVolume(track, volume.value);
    row.append(label, volume);
    for (const [action, toggle] of [['Mute', 'toggleMute'], ['Solo', 'toggleSolo']]) {
      const button = document.createElement('button');
      button.className = 'secondary';
      button.textContent = action;
      button.setAttribute('aria-label', `${action} ${name}`);
      button.setAttribute('aria-pressed', mixer.state[track][action === 'Mute' ? 'muted' : 'solo']);
      button.onclick = () => { mixer[toggle](track); renderMixer(); };
      row.append(button);
    }
    const button = document.createElement('button');
    button.textContent = 'Save WAV';
    button.setAttribute('aria-label', `Save ${name} WAV`);
    button.onclick = () => run(() => save(AudioConverter.encodeWav(mixer.stems[track]), `${fileTitle} - ${name}`, 'wav'));
    row.append(button);
    ui.tracks.append(row);
  }
  ui.mixPlay.textContent = mixer.isPlaying ? 'Pause mix' : 'Play mix';
  ui.backing.textContent = mixer.state.vocals.muted ? 'Restore vocals' : 'Mute vocals';
  ui.mix.hidden = false;
}

for (const preset of AudioFXEngine.PRESETS) ui.preset.add(new Option(preset.label, preset.id));
ui.modelLink.href = MODEL.url;
ui.file.onchange = () => {
  const file = ui.file.files[0];
  ui.file.value = '';
  if (file) void loadSource(file, file.name);
};
ui.capture.onclick = () => loadSource(job.item.url, job.title);
ui.from.oninput = ui.to.oninput = renderWaveform;
ui.wav.onclick = () => exportSelection('wav');
ui.mp3.onclick = () => exportSelection('mp3');
ui.cancel.onclick = () => {
  operation?.abort();
  ui.cancel.disabled = true;
  status('Cancelling…');
};
ui.preview.onclick = () => run(async () => {
  mixer.stop();
  stopPreview();
  previewUrl = URL.createObjectURL(AudioConverter.encodeWav(await selection()));
  ui.player.src = previewUrl;
  ui.player.hidden = false;
  await ui.player.play();
  status('Playing the selected audio.');
});
ui.model.onchange = () => {
  const file = ui.model.files[0];
  ui.model.value = '';
  if (file) void run(async () => {
    status('Verifying and saving the model…');
    await importOfflineModel(file);
    status('Model ready. Select audio and choose Split selection.');
  });
};
ui.split.onclick = () => run(async signal => {
  stopPreview();
  mixer.stop();
  status('Preparing your selection for separation…');
  const audio = await selection();
  signal.throwIfAborted();
  const stems = await StemEngine.separateViaBrowserOnnx(null, audio, ({ percent, stage }) => {
    signal.throwIfAborted();
    ui.progress.value = percent;
    status(stage);
  });
  signal.throwIfAborted();
  mixer.setTargetMode(ui.stemMode.value);
  mixer.loadStems(stems);
  renderMixer();
  status('Stems ready. Play the mix or save a track.');
}, { cancellable: true });
ui.mixPlay.onclick = async () => {
  try {
    if (mixer.isPlaying) mixer.pause();
    else {
      stopPreview();
      await AudioConverter.getAudioContext().resume();
      mixer.play();
    }
    ui.mixPlay.textContent = mixer.isPlaying ? 'Pause mix' : 'Play mix';
  } catch (error) { status(error.message, true); }
};
ui.backing.onclick = () => { mixer.toggleMute('vocals'); renderMixer(); };
ui.mixSave.onclick = () => run(() => {
  const audio = mixer.renderCustomMixBuffer();
  return save(AudioConverter.encodeWav(audio), `${fileTitle} - Mix`, 'wav');
});
window.addEventListener('beforeunload', event => {
  if (operation) { event.preventDefault(); event.returnValue = ''; }
});

const id = location.hash.slice(1);
if (/^export-[a-f0-9-]+$/.test(id)) {
  try {
    job = (await api.storage.session.get(id))[id];
    if (!job?.item?.url) throw new Error('Capture expired. Open the grabber again or choose a local file.');
    ui.capture.hidden = false;
    status(`Ready to load ${job.title}.`);
  } catch (error) { status(error.message, true); }
}
