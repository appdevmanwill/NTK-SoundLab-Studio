import { Input, UrlSource, BlobSource, ALL_FORMATS, AudioBufferSink, Output, StreamTarget, Conversion, Mp4OutputFormat, WavOutputFormat } from './lib/mediabunny.js';
import { mediaUrl } from './media-utils.mjs';

export async function inspectMedia(media, signal) {
  const source = media instanceof Blob ? new BlobSource(media) : new UrlSource(mediaUrl(media), {
    requestInit: { credentials: 'include' },
    maxCacheSize: 16 * 1024 * 1024,
    getRetryDelay: attempt => attempt < 2 ? attempt + 1 : null,
    fetchFn: async (resource, options) => {
      signal.throwIfAborted();
      const combined = AbortSignal.any([signal, options?.signal].filter(Boolean));
      const response = await fetch(resource, { ...options, signal: combined });
      if (!response.ok) throw new Error(`The source returned HTTP ${response.status}. Replay the media and capture its link again.`);
      const type = response.headers.get('content-type') || '';
      if (/text\/html|application\/json/i.test(type)) throw new Error('The source returned a page instead of media. Replay it and capture the playing stream.');
      return response;
    },
  });
  const input = new Input({ source, formats: ALL_FORMATS, hls: { offsetTimestampsByDateTime: false } });
  signal.addEventListener('abort', () => input.dispose(), { once: true });
  try {
    // Prefer the largest exposed video rendition, then its highest-bitrate audio.
    const videos = await input.getVideoTracks({ sortBy: async track => [-(await track.getDisplayWidth()) * (await track.getDisplayHeight()), -(await track.getBitrate() || 0)] });
    const video = videos[0] || null;
    const audios = await input.getAudioTracks({
      filter: track => !video || track.canBePairedWith(video),
      sortBy: async track => -(await track.getBitrate() || 0),
    });
    const audio = audios[0] || null;
    const tracks = [video, audio].filter(Boolean);
    if (!tracks.length) throw new Error('No supported media tracks were found. Capture a complete file or an HLS playlist.');
    if ((await Promise.all(tracks.map(track => track.isLive()))).some(Boolean)) {
      throw new Error('This stream is live. Capture the complete replay after it ends.');
    }
    const duration = await input.getDurationFromMetadata(tracks, { skipLiveWait: true });
    const details = {
      width: video ? await video.getDisplayWidth() : 0,
      height: video ? await video.getDisplayHeight() : 0,
      sampleRate: audio ? await audio.getSampleRate() : 0,
      channels: audio ? await audio.getNumberOfChannels() : 0,
      duration,
    };
    return { input, video, audio, details };
  } catch (error) {
    input.dispose();
    throw error;
  }
}

export async function writeMedia(media, format, writer, signal, onProgress = () => {}) {
  const { input, video, audio, details } = media;
  signal.throwIfAborted();
  if (format === 'mp3') {
    if (!audio) throw new Error('This stream has no audio. Choose an audio stream or a video with sound.');
    if (!await audio.canDecode()) throw new Error('This browser cannot decode the audio codec. Save the original file or use another supported browser.');
    const channels = Math.min(2, details.channels);
    const encoder = new globalThis.lamejs.Mp3Encoder(channels, details.sampleRate, 320);
    const sink = new AudioBufferSink(audio);
    let position = 0;
    for await (const { buffer, timestamp } of sink.buffers()) {
      signal.throwIfAborted();
      let pcm = buffer;
      if (buffer.numberOfChannels > 2) {
        const context = new OfflineAudioContext(2, buffer.length, buffer.sampleRate);
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(context.destination);
        source.start();
        pcm = await context.startRendering();
      }
      const samples = Array.from({ length: channels }, (_, channel) => {
        const data = pcm.getChannelData(channel);
        return Int16Array.from(data, sample => Math.round(Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767)));
      });
      const encoded = encoder.encodeBuffer(...samples);
      if (encoded.length) {
        await writer.write({ type: 'write', position, data: new Uint8Array(encoded.buffer, encoded.byteOffset, encoded.byteLength) });
        position += encoded.byteLength;
      }
      onProgress(details.duration ? Math.min(99, 100 * (timestamp + buffer.duration) / details.duration) : null);
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    const final = encoder.flush();
    if (final.length) await writer.write({ type: 'write', position, data: new Uint8Array(final.buffer, final.byteOffset, final.byteLength) });
    return;
  }

  if (format === 'video' && !video) throw new Error('This stream contains audio only. Select an audio export or capture a video stream.');
  if (format === 'wav' && !audio) throw new Error('This video has no audio track. Capture its accompanying audio stream.');
  const target = new StreamTarget(new WritableStream({ write: chunk => writer.write(chunk) }), { chunked: true, chunkSize: 1024 * 1024 });
  const output = new Output({ target, format: format === 'wav' ? new WavOutputFormat() : new Mp4OutputFormat({ fastStart: 'fragmented' }) });
  const conversion = await Conversion.init({
    input, output, tracks: 'all', showWarnings: false,
    copy: format === 'video' ? { mode: 'forced', shiftTolerance: Infinity } : false,
    video: track => ({ discard: format === 'wav' || track !== video }),
    audio: track => track !== audio ? { discard: true } : format === 'wav' ? { codec: 'pcm-s24' } : {},
  });
  const expected = format === 'wav' ? [audio] : [video, audio].filter(Boolean);
  if (!conversion.isValid || expected.some(track => !conversion.utilizedTracks.includes(track))) {
    await conversion.cancel();
    throw new Error('These tracks cannot be exported together in this format. Save the original file to retain all tracks and quality.');
  }
  const cancel = () => { void conversion.cancel().catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  conversion.onProgress = onProgress;
  try { await conversion.execute(); } finally { signal.removeEventListener('abort', cancel); }
}
