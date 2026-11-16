import { fetch, canUseLocalHelper } from './network-policy.js?v=2026.11.16.1';
/**
 * NTK SoundLab Studio - Hybrid Neural 4-Stem AI Separation Engine
 * Powered by Meta HTDemucs v4:
 *  - Tier 1 (Local Helper): Native PyTorch HTDemucs v4 via http://127.0.0.1:8899/api/stems/*
 *  - Tier 2 (Static Hosting - GitHub Pages / Firebase): In-Browser ONNX Runtime Web (WebGPU + WASM)
 *    running htdemucs_embedded.onnx cached permanently in IndexedDB.
 */

import { AudioConverter } from './audio-converter.js?v=2026.11.16.1';
import { VaultDB } from './vault-db.js?v=2026.11.16.1';
import { CONSTANTS, DemucsProcessor } from '../lib/demucs-web/index.js?v=2026.11.16.1';
import { ORT_DIRECTORY, ORT_SCRIPT, getVerifiedModel } from './offline-model.js?v=2026.11.16.1';

export class StemEngine {
  static LOCAL_BASE = 'http://127.0.0.1:8899';
  static _activeBase = '';
  static _browserSession = null;
  static _ortPromise = null;

  /**
   * Probes whether the local Python helper supports native HTDemucs separation
   * @returns {Promise<{ available: boolean, device: string, engine: string }>}
   */
  static async checkLocalDemucs() {
    // Tier 0: Same-Origin Backend
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 1200);
      const res = await fetch('/api/stems/capabilities', { signal: controller.signal });
      clearTimeout(timer);
      if (res.ok) {
        const data = await res.json();
        StemEngine._activeBase = '';
        return {
          available: Boolean(data.available),
          device: data.device || 'browser',
          engine: data.engine || 'In-Browser ONNX WebGPU/WASM'
        };
      }
    } catch (e) {}

    // Tier 1: Local Python Helper on Port 8899 (only if not on a server or if local active)
    if (canUseLocalHelper() && window.location.port !== '8899') {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 1400);
        const res = await fetch(`${StemEngine.LOCAL_BASE}/api/stems/capabilities`, {
          signal: controller.signal
        });
        clearTimeout(timer);
        if (res.ok) {
          const data = await res.json();
          StemEngine._activeBase = StemEngine.LOCAL_BASE;
          return {
            available: Boolean(data.available),
            device: data.device || 'cpu',
            engine: data.engine || 'htdemucs-v4'
          };
        }
      } catch (e) {}
    }
    return { available: false, device: 'none', engine: 'In-Browser ONNX WebGPU/WASM' };
  }

  /**
   * Dynamically loads ONNX Runtime Web (WebGPU + SIMD WASM) safely on static hosts without COOP/COEP
   */
  static async loadOnnxRuntime() {
    if (window.ort) return window.ort;
    if (StemEngine._ortPromise) return StemEngine._ortPromise;

    StemEngine._ortPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = ORT_SCRIPT;
      script.async = true;
      script.onload = () => {
        if (!window.ort) {
          StemEngine._ortPromise = null;
          reject(new Error('ONNX Runtime loaded without its API. Retry after checking the connection.'));
          return;
        }
        window.ort.env.wasm.wasmPaths = ORT_DIRECTORY.href;
        // Avoid SharedArrayBuffer crash on GitHub Pages / static hosts lacking COOP/COEP headers
        window.ort.env.wasm.numThreads = window.crossOriginIsolated
          ? Math.min(4, navigator.hardwareConcurrency || 2)
          : 1;
        window.ort.env.wasm.simd = true;
        resolve(window.ort);
      };
      script.onerror = () => {
        script.remove();
        StemEngine._ortPromise = null;
        reject(new Error('The neural runtime is unavailable. Open the packaged app or prepare the offline model from an online browser session.'));
      };
      document.head.appendChild(script);
    });

    return StemEngine._ortPromise;
  }

  /**
   * Decodes 4 WAV ArrayBuffers into AudioBuffers and builds a clean Instrumental sum (Drums + Bass + Other)
   */
  static async buildStemBundleFromWavs(wavBundle, engineLabel) {
    const promises = [
      AudioConverter.decodeAudioData(wavBundle.vocalsWav),
      AudioConverter.decodeAudioData(wavBundle.drumsWav),
      AudioConverter.decodeAudioData(wavBundle.bassWav),
      AudioConverter.decodeAudioData(wavBundle.otherWav)
    ];

    if (wavBundle.leadVocalsWav && wavBundle.backingVocalsWav) {
      promises.push(
        AudioConverter.decodeAudioData(wavBundle.leadVocalsWav),
        AudioConverter.decodeAudioData(wavBundle.backingVocalsWav)
      );
    }

    const decoded = await Promise.all(promises);
    const vocals = decoded[0];
    const drums = decoded[1];
    const bass = decoded[2];
    const other = decoded[3];
    const lead_vocals = decoded[4] || null;
    const backing_vocals = decoded[5] || null;

    const instrumental = AudioConverter.mixStems(
      { vocals, drums, bass, other },
      { vocals: 0, drums: 1, bass: 1, other: 1 },
      true
    );

    return {
      engine: engineLabel,
      vocals,
      lead_vocals,
      backing_vocals,
      drums,
      bass,
      other,
      instrumental
    };
  }

  /**
   * Separates an isolated vocal AudioBuffer into Lead Vocals and Backing Harmonies
   * @param {AudioBuffer} vocalBuffer
   * @param {Function} [onProgress]
   * @returns {Promise<{ leadVocals: AudioBuffer, backingVocals: AudioBuffer, engine: string }>}
   */
  static async splitLeadAndBackingVocals(vocalBuffer, onProgress = () => {}) {
    onProgress(10, 'Checking local vocal demixing helper...');
    // Attempt 1: Local PyTorch Server
    try {
      const wavBytes = AudioConverter.encodeWavArrayBuffer(vocalBuffer);
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 20000);
      const res = await fetch(`${StemEngine._activeBase}/api/stems/split-vocals`, {
        method: 'POST',
        headers: { 'Content-Type': 'audio/wav' },
        body: wavBytes,
        signal: controller.signal
      });
      clearTimeout(timer);
      if (res.ok) {
        onProgress(60, 'Decoding separated lead and backing stems...');
        const json = await res.json();
        if (json.lead_wav_base64 && json.backing_wav_base64) {
          const leadRaw = Uint8Array.from(atob(json.lead_wav_base64), (c) => c.charCodeAt(0)).buffer;
          const backRaw = Uint8Array.from(atob(json.backing_wav_base64), (c) => c.charCodeAt(0)).buffer;
          const [leadVocals, backingVocals] = await Promise.all([
            AudioConverter.decodeAudioData(leadRaw),
            AudioConverter.decodeAudioData(backRaw)
          ]);
          onProgress(100, 'Vocal demixing complete (PyTorch)!');
          return { leadVocals, backingVocals, engine: 'PyTorch Neural Demix' };
        }
      }
    } catch (e) {}

    // Attempt 2: High-Resolution In-Browser Center-Harmonic Demixing
    onProgress(35, 'Running in-browser Center-Harmonic demixing...');
    const sr = vocalBuffer.sampleRate;
    const len = vocalBuffer.length;
    const numCh = vocalBuffer.numberOfChannels;
    const leadBuf = AudioConverter.createBuffer(2, len, sr);
    const backBuf = AudioConverter.createBuffer(2, len, sr);

    const chL = vocalBuffer.getChannelData(0);
    const chR = numCh > 1 ? vocalBuffer.getChannelData(1) : chL;

    const leadL = leadBuf.getChannelData(0);
    const leadR = leadBuf.getChannelData(1);
    const backL = backBuf.getChannelData(0);
    const backR = backBuf.getChannelData(1);

    const chunkSize = 2048;
    for (let idx = 0; idx < len; idx++) {
      if (idx % 80000 === 0) {
        const pct = 35 + Math.round((idx / len) * 60);
        onProgress(pct, `Extracting lead & backing harmonics (${pct}%)...`);
        await new Promise((r) => setTimeout(r, 0));
      }

      const sL = chL[idx];
      const sR = chR[idx];
      const sumMid = 0.5 * (sL + sR);
      const sumSq = sL * sL + sR * sR + 1e-7;
      const correlation = Math.max(0, (2 * sL * sR) / sumSq);
      const centerFactor = Math.pow(correlation, 1.4);

      const leadSample = sumMid * centerFactor;
      leadL[idx] = leadSample;
      leadR[idx] = leadSample;

      backL[idx] = sL - leadSample;
      backR[idx] = sR - leadSample;
    }

    onProgress(100, 'In-browser vocal demixing complete!');
    return { leadVocals: leadBuf, backingVocals: backBuf, engine: 'Browser Center Harmonic Demix' };
  }

  /**
   * Main entry point: Separates an AudioBuffer into 4 neural stems (vocals, drums, bass, other + instrumental)
   *
   * @param {string} uuid - Song UUID for IndexedDB caching
   * @param {AudioBuffer} sourceBuffer - Decoded master AudioBuffer
   * @param {Object} [options]
   * @param {'auto'|'local'|'browser'} [options.mode='auto']
   * @param {boolean} [options.forceRecompute=false]
   * @param {Function} [options.onProgress] - ({ percent, stage, engine })
   * @returns {Promise<{ engine: string, vocals: AudioBuffer, drums: AudioBuffer, bass: AudioBuffer, other: AudioBuffer, instrumental: AudioBuffer }>}
   */
  static async separate(uuid, sourceBuffer, options = {}) {
    const mode = options.mode || 'auto';
    const forceRecompute = Boolean(options.forceRecompute);
    const onProgress = options.onProgress || (() => {});

    // 1. Check IndexedDB Vault first unless user requested fresh separation
    if (!forceRecompute && uuid) {
      const cachedStems = await VaultDB.getStems(uuid);
      if (
        cachedStems &&
        cachedStems.vocalsWav &&
        cachedStems.drumsWav &&
        cachedStems.bassWav &&
        cachedStems.otherWav
      ) {
        onProgress({
          percent: 95,
          stage: 'Restoring 4 separated neural stems from Offline Vault...',
          engine: cachedStems.engine || 'vault-htdemucs'
        });
        const bundle = await StemEngine.buildStemBundleFromWavs(
          cachedStems,
          cachedStems.engine || 'htdemucs-v4'
        );
        onProgress({
          percent: 100,
          stage: 'Loaded 4 neural stems from Offline Vault!',
          engine: bundle.engine
        });
        return bundle;
      }
    }

    // 2. Determine whether to use Local Native PyTorch HTDemucs or In-Browser ONNX HTDemucs
    let useLocal = false;
    let localCaps = { available: false, device: 'cpu' };

    if (mode === 'local' || mode === 'auto') {
      localCaps = await StemEngine.checkLocalDemucs();
      if (localCaps.available) {
        useLocal = true;
      } else if (mode === 'local') {
        throw new Error(
          'Local Python HTDemucs engine is not running on port 8899. Switch to Auto/In-Browser AI or start helper/suno_helper.py --serve.'
        );
      }
    }

    if (useLocal) {
      return await StemEngine.separateViaLocalHelper(uuid, sourceBuffer, localCaps, onProgress);
    }
    return await StemEngine.separateViaBrowserOnnx(uuid, sourceBuffer, onProgress);
  }

  /**
   * Tier 1: Native PyTorch HTDemucs v4 on Local Helper Server (Port 8899)
   */
  static async separateViaLocalHelper(uuid, sourceBuffer, localCaps, onProgress) {
    const engineLabel = `HTDemucs v4 (Local ${String(localCaps.device || 'CPU').toUpperCase()})`;

    onProgress({
      percent: 3,
      stage: 'Resampling master audio to 44.1 kHz stereo...',
      engine: engineLabel
    });

    const stereo44k = await AudioConverter.resampleToStereo(sourceBuffer, 44100);
    const wavArrayBuf = AudioConverter.encodeWavArrayBuffer(stereo44k);

    onProgress({
      percent: 6,
      stage: `Sending waveform to local ${engineLabel} engine...`,
      engine: engineLabel
    });

    const startResp = await fetch(`${StemEngine._activeBase}/api/stems/separate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'audio/wav',
        'X-Song-Id': uuid || 'unknown'
      },
      body: wavArrayBuf
    });

    if (!startResp.ok) {
      let msg = `Local stem server returned HTTP ${startResp.status}`;
      try {
        const errJson = await startResp.json();
        if (errJson.error) msg = errJson.error;
      } catch (e) {}
      throw new Error(msg);
    }

    const { job_id: jobId } = await startResp.json();

    // Poll job progress
    while (true) {
      await new Promise(r => setTimeout(r, 450));
      const statusResp = await fetch(`${StemEngine._activeBase}/api/stems/status/${jobId}`);
      if (!statusResp.ok) {
        throw new Error(`Lost connection to local stem job (${statusResp.status})`);
      }
      const info = await statusResp.json();

      if (info.status === 'error') {
        throw new Error(info.error || 'Local HTDemucs separation failed');
      }

      onProgress({
        percent: Math.min(93, Math.max(8, Number(info.progress) || 10)),
        stage: info.stage || 'Running HTDemucs v4 neural network...',
        engine: engineLabel
      });

      if (info.status === 'done') {
        break;
      }
    }

    onProgress({
      percent: 95,
      stage: 'Downloading 4 studio-isolated WAV stems...',
      engine: engineLabel
    });

    const fetchStemWav = async (stemName) => {
      const r = await fetch(`${StemEngine._activeBase}/api/stems/download/${jobId}/${stemName}`);
      if (!r.ok) throw new Error(`Failed to fetch separated ${stemName} stem`);
      return await r.arrayBuffer();
    };

    const [vocalsWav, drumsWav, bassWav, otherWav] = await Promise.all([
      fetchStemWav('vocals'),
      fetchStemWav('drums'),
      fetchStemWav('bass'),
      fetchStemWav('other')
    ]);

    const wavBundle = { engine: engineLabel, vocalsWav, drumsWav, bassWav, otherWav };
    if (uuid) {
      await VaultDB.saveStems(uuid, wavBundle);
    }

    onProgress({
      percent: 98,
      stage: 'Initializing 4-track synchronized studio console...',
      engine: engineLabel
    });

    const result = await StemEngine.buildStemBundleFromWavs(wavBundle, engineLabel);
    onProgress({
      percent: 100,
      stage: '4-Stem Neural Separation Complete!',
      engine: engineLabel
    });
    return result;
  }

  /**
   * Tier 2: Pure Static In-Browser Neural AI (ONNX Runtime Web + WebGPU/WASM + htdemucs_embedded.onnx)
   */
  static browserSession(onProgress) {
    if (!StemEngine._browserSession) {
      StemEngine._browserSession = StemEngine.initializeBrowserSession(onProgress).catch(error => {
        StemEngine._browserSession = null;
        throw error;
      });
    }
    return StemEngine._browserSession;
  }

  static async initializeBrowserSession(onProgress) {
    onProgress({ percent: 2, stage: 'Loading the bundled neural runtime…' });
    const ort = await StemEngine.loadOnnxRuntime();
    const model = await getVerifiedModel(ratio => onProgress({
      percent: Math.round(4 + ratio * 24),
      stage: `Loading the HTDemucs model · ${Math.round(ratio * 100)}%`,
    }));
    const create = async (providers, engineLabel) => {
      onProgress({ percent: 29, stage: `Preparing ${engineLabel}…`, engine: engineLabel });
      const processor = new DemucsProcessor({
        ort, sessionOptions: { executionProviders: providers, graphOptimizationLevel: 'all' },
      });
      await processor.loadModel(model);
      return { processor, engineLabel };
    };
    try {
      const adapter = await navigator.gpu?.requestAdapter();
      // The pinned runtime produced out-of-range stem samples on Intel Gen 9.
      const useWasm = adapter?.info?.vendor === 'intel' && adapter.info.architecture === 'gen-9';
      if (adapter && !useWasm) {
        return await create(['webgpu', 'wasm'], 'HTDemucs v4 (WebGPU with WASM fallback)');
      }
    } catch {
      onProgress({ percent: 29, stage: 'WebGPU initialization failed. Trying WASM…' });
    }
    return create(['wasm'], 'HTDemucs v4 (WASM SIMD)');
  }

  static async separateViaBrowserOnnx(uuid, sourceBuffer, onProgress) {
    const { processor, engineLabel } = await StemEngine.browserSession(onProgress);

    onProgress({
      percent: 32,
      stage: 'Resampling audio to 44.1 kHz stereo...',
      engine: engineLabel
    });

    const stereo44k = await AudioConverter.resampleToStereo(sourceBuffer, CONSTANTS.SAMPLE_RATE);
    const leftIn = stereo44k.getChannelData(0);
    const rightIn = stereo44k.getChannelData(1);

    processor.onProgress = ({ progress, currentSegment, totalSegments }) => {
      const pct = Math.min(95, 34 + Math.round(progress * 61));
      onProgress({
        percent: pct,
        stage: `In-Browser HTDemucs segment ${currentSegment} / ${totalSegments} (${Math.round(progress * 100)}%)...`,
        engine: engineLabel
      });
    };

    const rawOut = await processor.separate(leftIn, rightIn);

    onProgress({
      percent: 96,
      stage: 'Packaging 4 isolated stems & caching to Offline Vault...',
      engine: engineLabel
    });

    const sr = CONSTANTS.SAMPLE_RATE;
    const vocals = AudioConverter.channelsToAudioBuffer(rawOut.vocals.left, rawOut.vocals.right, sr);
    const drums = AudioConverter.channelsToAudioBuffer(rawOut.drums.left, rawOut.drums.right, sr);
    const bass = AudioConverter.channelsToAudioBuffer(rawOut.bass.left, rawOut.bass.right, sr);
    const other = AudioConverter.channelsToAudioBuffer(rawOut.other.left, rawOut.other.right, sr);

    const instrumental = AudioConverter.mixStems(
      { vocals, drums, bass, other },
      { vocals: 0, drums: 1, bass: 1, other: 1 },
      true
    );

    if (uuid) {
      await VaultDB.saveStems(uuid, {
        engine: engineLabel,
        vocalsWav: AudioConverter.encodeWavArrayBuffer(vocals),
        drumsWav: AudioConverter.encodeWavArrayBuffer(drums),
        bassWav: AudioConverter.encodeWavArrayBuffer(bass),
        otherWav: AudioConverter.encodeWavArrayBuffer(other)
      });
    }

    onProgress({
      percent: 100,
      stage: '4-Stem In-Browser Neural Separation Complete!',
      engine: engineLabel
    });

    return {
      engine: engineLabel,
      vocals,
      drums,
      bass,
      other,
      instrumental
    };
  }
}
