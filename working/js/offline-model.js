import { fetch } from './network-policy.js?v=2026.11.11.2';
import { VaultDB } from './vault-db.js?v=2026.11.11.2';

export const MODEL = Object.freeze({
  id: 'htdemucs_embedded_92e33df6',
  bytes: 180534758,
  sha256: 'e5e425c17683f163a472462eb5f5a4ffcd11c31858d57fbd0833b012d8b88077',
  filename: 'htdemucs_embedded.onnx',
  url: 'https://huggingface.co/timcsy/demucs-web-onnx/resolve/92e33df61cfc9eb820272aaa62d2ef6dcf4d950d/htdemucs_embedded.onnx',
});
export const ORT_DIRECTORY = new URL('../lib/onnxruntime/1.20.1/', import.meta.url);
export const ORT_SCRIPT = new URL('ort.webgpu.min.js', ORT_DIRECTORY).href;
const RUNTIME_CACHE = 'ntk-soundlab-onnx-1.20.1';
const RUNTIME_FILES = [
  ORT_SCRIPT,
  new URL('ort-wasm-simd-threaded.jsep.mjs', ORT_DIRECTORY).href,
  new URL('ort-wasm-simd-threaded.jsep.wasm', ORT_DIRECTORY).href,
];
const LEGACY_MODEL_ID = 'htdemucs_embedded_v1';

async function verifyModel(buffer) {
  if (buffer.byteLength !== MODEL.bytes) {
    throw new Error('This file has the wrong size. Choose the SoundLab HTDemucs model listed in Offline Storage.');
  }
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', buffer));
  const sha256 = Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('');
  if (sha256 !== MODEL.sha256) {
    throw new Error('The model checksum did not match. Choose a verified copy of the SoundLab model.');
  }
  return buffer;
}

async function cacheRuntime() {
  // Native Android serves this runtime directly from bundled app assets.
  if (window.AndroidStudio || location.port === '47831') return;
  if (!globalThis.caches) throw new Error('This browser cannot prepare the offline neural runtime.');
  const cache = await caches.open(RUNTIME_CACHE);
  const matches = await Promise.all(RUNTIME_FILES.map(url => cache.match(url)));
  const missing = RUNTIME_FILES.filter((_, index) => !matches[index]);
  if (missing.length) await cache.addAll(missing);
}

export async function importOfflineModel(file) {
  if (file.size !== MODEL.bytes) throw new Error('Choose the verified HTDemucs model file (180 MB).');
  await verifyModel(await file.arrayBuffer());
  await cacheRuntime();
  if (!await VaultDB.saveAiModel(MODEL.id, file)) {
    throw new Error('The model could not be saved. Free some browser storage or use a desktop sidecar.');
  }
}

async function readResponse(response, onProgress) {
  if (!response.ok || !response.body) throw new Error(`Could not load the neural model (HTTP ${response.status}).`);
  const reader = response.body.getReader();
  const bytes = new Uint8Array(MODEL.bytes);
  let offset = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      if (offset + value.byteLength > bytes.byteLength) throw new Error('The model download exceeds its expected size.');
      bytes.set(value, offset);
      offset += value.byteLength;
      onProgress(offset / bytes.byteLength);
    }
    if (offset !== bytes.byteLength) throw new Error('The model download was incomplete.');
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  return verifyModel(bytes.buffer);
}

export async function getVerifiedModel(onProgress) {
  for (const id of [MODEL.id, LEGACY_MODEL_ID]) {
    const stored = await VaultDB.getAiModel(id);
    if (!stored) continue;
    try {
      await verifyModel(stored);
      return stored;
    } catch {
      // Leave existing data intact. An invalid cache entry is never passed to ONNX.
    }
  }

  const sidecar = new URL(`../models/${MODEL.filename}`, import.meta.url).href;
  const local = await fetch(sidecar, { method: 'HEAD', timeoutMs: 3000 }).catch(() => null);
  if (local?.ok && Number(local.headers.get('Content-Length')) === MODEL.bytes) {
    return readResponse(await fetch(sidecar, { timeoutMs: 300000 }), onProgress);
  }
  if (!navigator.onLine) {
    throw new Error('Import the verified HTDemucs file from Offline Storage to separate stems offline.');
  }
  const response = await fetch(MODEL.url, { timeoutMs: 300000, cache: 'no-store' });
  const buffer = await readResponse(response, onProgress);
  if (await VaultDB.saveAiModel(MODEL.id, buffer)) await cacheRuntime().catch(() => {});
  return buffer;
}
