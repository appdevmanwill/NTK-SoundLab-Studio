import { fetch, canUseLocalHelper } from './network-policy.js?v=2026.11.16.1';
/**
 * NTK SoundLab Studio - Universal Stream & Link Resolver
 * Multi-tier connectivity: Same-Origin Laravel Server -> Local OmniHelper -> In-Browser Fallbacks
 */

export class SoundLabAPI {
  static LOCAL_PROXY_URL = 'http://127.0.0.1:8899';
  static SUNO_UUID_REGEX = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
  static SUNO_PLAYLIST_REGEX = /(?:suno\.com\/playlist\/|[?&]playlist=)([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;
  static YOUTUBE_REGEX = /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/|playlist\?list=))([a-zA-Z0-9_-]{11,34})/i;
  static TIKTOK_REGEX = /tiktok\.com\/@?[a-zA-Z0-9_.-]+\/video\/(\d+)|vm\.tiktok\.com\/[a-zA-Z0-9_-]+/i;
  static SOUNDCLOUD_REGEX = /soundcloud\.com\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_-]+/i;

  static _localActive = null;

  /**
   * Probes whether the Laravel backend or local Python helper is running
   * @returns {Promise<{ active: boolean, ytdl: boolean, ffmpeg: boolean, demucs: Object }>}
   */
  static async checkLocalHelper() {
    // Tier 0: Same-Origin Laravel Server
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 5000);
      const res = await fetch('/api/capabilities', { signal: controller.signal });
      clearTimeout(timer);
      if (res.ok) {
        const data = await res.json();
        SoundLabAPI._localActive = true;
        return {
          active: true,
          server: data.server || 'Laravel Server',
          ytdl: Boolean(data.yt_dlp),
          ffmpeg: Boolean(data.ffmpeg),
          demucs: data.demucs || { available: false, engine: 'In-Browser ONNX WebGPU/WASM' }
        };
      }
    } catch (e) {}

    // Tier 1: Local Python OmniHelper on port 8899 (only if running as static PWA or file:)
    if (canUseLocalHelper()) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 2000);
        const res = await fetch(`${SoundLabAPI.LOCAL_PROXY_URL}/api/capabilities`, {
          signal: controller.signal
        });
        clearTimeout(timer);
        if (res.ok) {
          const data = await res.json();
          SoundLabAPI._localActive = true;
          return {
            active: true,
            server: 'Local Python Helper',
            ytdl: Boolean(data.ytdl || data.yt_dlp),
            ffmpeg: Boolean(data.ffmpeg),
            demucs: data.demucs || { available: false }
          };
        }
      } catch (e) {
        SoundLabAPI._localActive = false;
      }
    }

    return {
      active: false,
      ytdl: false,
      ffmpeg: false,
      demucs: { available: false, engine: 'In-Browser ONNX WebGPU/WASM' }
    };
  }

  /**
   * Sanitizes URLs by stripping tracking queries and canonicalizing shortlinks
   * @param {string} raw
   * @returns {string}
   */
  static cleanUrl(raw) {
    const clean = String(raw || '').trim();
    if (!clean) return '';
    if (/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(clean)) return clean.toLowerCase();
    try {
      const u = new URL(clean);
      if (!['http:', 'https:'].includes(u.protocol) || u.username || u.password) throw new Error('Invalid media URL');
      if (u.hostname === 'youtu.be' && /^\/[a-zA-Z0-9_-]{11}\/?$/.test(u.pathname)) {
        return `https://www.youtube.com/watch?v=${u.pathname.split('/')[1]}`;
      }
      if (u.hostname === 'm.youtube.com') u.hostname = 'www.youtube.com';
      if (u.hostname === 'instagr.am') u.hostname = 'www.instagram.com';
      if (u.hostname === 'fxtwitter.com' || u.hostname === 'vxtwitter.com') u.hostname = 'x.com';
      if (u.hostname === 'dai.ly' && /^\/[a-zA-Z0-9]+\/?$/.test(u.pathname)) {
        return `https://www.dailymotion.com/video/${u.pathname.replace(/\//g, '')}`;
      }
      // Preserve query parameters: a direct media URL may be signed.
      return u.toString();
    } catch (e) {
      throw new Error('Use a public HTTP or HTTPS media link, or a Suno song UUID.');
    }
  }

  /**
   * Classifies an input string into platform and type
   * @param {string} input
   * @returns {{ platform: string, isPlaylist: boolean, isDrm?: boolean, raw: string }}
   */
  static classifyUrl(input) {
    const s = String(input || '').trim();
    if (!s) return { platform: 'Unknown', isPlaylist: false, raw: s };

    let parsed;
    try { parsed = new URL(s); } catch {}
    const host = parsed?.hostname.toLowerCase() || '';
    const belongsTo = domain => host === domain || host.endsWith('.' + domain);

    // Suno AI detection (playlists, songs, short links, or bare UUIDs)
    if (belongsTo('suno.com') || belongsTo('suno.ai') || /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(s)) {
      const isPlaylist = parsed?.pathname.startsWith('/playlist/') || false;
      return { platform: 'Suno AI', isPlaylist, raw: s };
    }
    if (belongsTo('acemusic.ai')) {
      return { platform: 'ACE Music', isPlaylist: false, raw: s };
    }
    if (belongsTo('flowmusic.app') || belongsTo('riffusion.com') || belongsTo('producer.ai')) {
      return { platform: 'Flow Music', isPlaylist: false, raw: s };
    }
    if (belongsTo('treblo.com') || belongsTo('sonauto.ai')) {
      return { platform: 'Treblo', isPlaylist: false, raw: s };
    }
    if (belongsTo('audius.co')) {
      return { platform: 'Audius', isPlaylist: s.includes('/playlist/') || s.includes('/album/'), raw: s };
    }
    if (belongsTo('vocaroo.com') || belongsTo('voca.ro')) {
      return { platform: 'Vocaroo', isPlaylist: false, raw: s };
    }
    if (host.startsWith('music.amazon.')) {
      return { platform: 'Amazon Music', isPlaylist: false, isDrm: true, raw: s };
    }
    for (const [domain, label] of [
      ['audiomack.com', 'Audiomack'],
      ['spotify.com', 'Spotify'],
      ['music.apple.com', 'Apple Music'],
      ['itunes.apple.com', 'Apple Music'],
      ['tidal.com', 'Tidal'],
      ['deezer.com', 'Deezer'],
      ['pandora.com', 'Pandora'],
      ['boomplay.com', 'Boomplay']
    ]) {
      if (belongsTo(domain)) {
        return { platform: label, isPlaylist: s.includes('/album/') || s.includes('/playlist/'), isDrm: true, raw: s };
      }
    }
    if (belongsTo('youtube.com') || host === 'youtu.be') {
      return { platform: 'YouTube', isPlaylist: s.includes('list='), raw: s };
    }
    if (belongsTo('tiktok.com')) {
      return { platform: 'TikTok', isPlaylist: false, raw: s };
    }
    if (belongsTo('soundcloud.com') || belongsTo('snd.sc')) {
      return { platform: 'SoundCloud', isPlaylist: s.includes('/sets/'), raw: s };
    }
    if (belongsTo('bandcamp.com')) {
      return { platform: 'Bandcamp', isPlaylist: s.includes('/album/'), raw: s };
    }
    if (belongsTo('mixcloud.com')) {
      return { platform: 'Mixcloud', isPlaylist: false, raw: s };
    }
    if (belongsTo('freesound.org')) {
      return { platform: 'Freesound', isPlaylist: false, raw: s };
    }
    if (belongsTo('jamendo.com')) {
      return { platform: 'Jamendo', isPlaylist: s.includes('/album/'), raw: s };
    }
    if (belongsTo('archive.org')) {
      return { platform: 'Internet Archive', isPlaylist: false, raw: s };
    }
    if (belongsTo('dailymotion.com') || host === 'dai.ly') {
      return { platform: 'Dailymotion', isPlaylist: false, raw: s };
    }
    if (belongsTo('twitch.tv')) {
      return { platform: 'Twitch', isPlaylist: false, raw: s };
    }
    if (belongsTo('bilibili.com') || belongsTo('b23.tv')) {
      return { platform: 'Bilibili', isPlaylist: false, raw: s };
    }
    if (belongsTo('instagram.com') || host === 'instagr.am') {
      return { platform: 'Instagram', isPlaylist: false, raw: s };
    }
    if (belongsTo('twitter.com') || belongsTo('x.com') || belongsTo('fxtwitter.com') || belongsTo('vxtwitter.com')) {
      return { platform: 'Twitter/X', isPlaylist: false, raw: s };
    }
    if (belongsTo('vimeo.com')) {
      return { platform: 'Vimeo', isPlaylist: false, raw: s };
    }
    if (belongsTo('facebook.com') || host === 'fb.watch') {
      return { platform: 'Facebook', isPlaylist: false, raw: s };
    }
    if (/\.(m3u8|mpd)$/i.test(parsed?.pathname || '')) {
      return { platform: 'HLS/DASH Stream', isPlaylist: false, raw: s };
    }
    if (/\.(mp3|wav|m4a|aac|mp4|webm|flac|ogg|opus)$/i.test(parsed?.pathname || '')) {
      return { platform: 'Direct Media File', isPlaylist: false, raw: s };
    }
    return { platform: 'Universal Web', isPlaylist: false, raw: s };
  }

  /**
   * Resolves universal metadata for any link
   * @param {string} url
   * @returns {Promise<Object>}
   */
  static async resolveUrl(url) {
    const clean = SoundLabAPI.cleanUrl(url);
    if (!clean) throw new Error('Empty URL provided.');

    const classification = SoundLabAPI.classifyUrl(clean);

    // Fast-path: Suno AI tracks resolve directly via clip proxy / direct Suno API
    if (classification.platform === 'Suno AI') {
      return SoundLabAPI.resolveSunoDirect(clean);
    }

    const q = encodeURIComponent(clean);
    let serverMessage = '';
    let rejected = false;

    // Tier 0: Same-Origin Backend Server
    try {
      const res = await fetch(`/api/omni/resolve?url=${q}`);
      if (res.ok) {
        const data = await res.json();
        if (data && !data.error) {
          return data;
        }
      } else {
        const errBody = (await res.json().catch(() => null))?.error || '';
        if ([400, 403, 422].includes(res.status)) {
          serverMessage = errBody || serverMessage;
          rejected = res.status !== 422;
        } else if ([404, 501, 503].includes(res.status) && errBody) {
          serverMessage = errBody;
        }
      }
    } catch (e) {}
    if (rejected) throw new Error(serverMessage || 'This media address is not permitted.');

    // Tier 1: Local Python OmniHelper (only allowed from loopback/file origins)
    if (canUseLocalHelper()) {
      try {
        const res = await fetch(`${SoundLabAPI.LOCAL_PROXY_URL}/api/omni/resolve?url=${q}`);
        const data = await res.json().catch(() => null);
        if (res.ok && data && !data.error) {
          const rewriteLocalPaths = (obj) => {
            if (!obj || typeof obj !== 'object') return;
            for (const key of ['streamUrl', 'direct_stream_url', 'imageLarge', 'imageThumb', 'image_url']) {
              if (typeof obj[key] === 'string' && obj[key].startsWith('/api/')) {
                obj[key] = `${SoundLabAPI.LOCAL_PROXY_URL}${obj[key]}`;
              }
            }
          };
          rewriteLocalPaths(data);
          if (Array.isArray(data.clips)) {
            data.clips.forEach(rewriteLocalPaths);
          }
          return data;
        }
        if (data && data.error) {
          serverMessage = data.error;
        }
      } catch (e) {}
    }

    // Tier 2: Direct media URL fallback
    if (classification.platform === 'Direct Media File') {
      const filename = new URL(clean).pathname.split('/').pop() || 'Media_Track';
      const ext = filename.split('.').pop().toLowerCase();
      const isVid = ['mp4', 'webm', 'mov'].includes(ext);
      const id = `direct-${crypto.randomUUID()}`;
      let title = filename.replace(/\.[^/.]+$/, '');
      try { title = decodeURIComponent(title); } catch {}
      return {
        type: 'single',
        uuid: id,
        id,
        title,
        artist: 'Web Media Stream',
        duration: 0,
        imageLarge: '',
        imageThumb: '',
        streamUrl: clean,
        url: clean,
        platform: 'Direct Media File',
        hasVideo: isVid,
        hasAudio: true,
        hasStem: true,
        tags: `${ext.toUpperCase()} Stream`
      };
    }

    if (serverMessage) {
      throw new Error(serverMessage);
    }
    if (classification.platform === 'Audiomack') {
      throw new Error('Audiomack requires signed OAuth playback credentials and its legacy public extractor API is unavailable. Play the track directly in Audiomack or import a local MP3/WAV/FLAC/M4A file into SoundLab Studio.');
    }
    if (classification.isDrm) {
      throw new Error(`${classification.platform} streams are DRM-protected and require an official ${classification.platform} license. Please import a local MP3/WAV/FLAC/M4A file into SoundLab Studio.`);
    }
    if (classification.platform === 'HLS/DASH Stream') {
      throw new Error('HLS/DASH playlist manifests (.m3u8/.mpd) require FFmpeg/yt-dlp remuxing. Open this link with the local Python helper (OmniHelper) or import a local audio/video file.');
    }
    if (['ACE Music', 'Flow Music', 'Treblo', 'Audius', 'Vocaroo'].includes(classification.platform)) {
      throw new Error(`${classification.platform} requires SoundLab Desktop, the PHP server, or the local Python helper to proxy audio across browser CORS boundaries. Import the downloaded audio file locally on static web.`);
    }
    throw new Error(`Could not resolve "${classification.platform}" link. Use an available download service or import a local file.`);
  }

  /**
   * Direct Suno resolver with local proxy priority & shortlink unshortening
   */
  static async resolveSunoDirect(input) {
    let match = input.match(SoundLabAPI.SUNO_UUID_REGEX);
    let uuid = match ? match[0].toLowerCase() : null;

    if (!uuid) {
      const q = encodeURIComponent(input);

      // Attempt 1: Dedicated Suno unshortener
      try {
        const uRes = await fetch(`/api/suno/unshorten?url=${q}`);
        if (uRes.ok) {
          const uData = await uRes.json();
          if (uData && uData.uuid) {
            uuid = uData.uuid.toLowerCase();
          }
        }
      } catch (e) {}

      // Attempt 2: Universal resolver endpoint
      if (!uuid) {
        try {
          const oRes = await fetch(`/api/omni/resolve?url=${q}`);
          if (oRes.ok) {
            const oData = await oRes.json();
            if (oData && oData.uuid && SoundLabAPI.SUNO_UUID_REGEX.test(oData.uuid)) {
              return oData;
            }
          }
        } catch (e) {}
      }

      // Attempt 3: Local helper proxy (same-machine loopback only)
      if (!uuid && canUseLocalHelper()) {
        try {
          const lRes = await fetch(`${SoundLabAPI.LOCAL_PROXY_URL}/api/suno/unshorten?url=${q}`);
          if (lRes.ok) {
            const lData = await lRes.json();
            if (lData && lData.uuid) {
              uuid = lData.uuid.toLowerCase();
            }
          }
        } catch (e) {}
      }

      if (!uuid) {
        throw new Error(`Could not find Suno UUID in: ${input}`);
      }
    }

    // Check playlist across desktop, Laravel, and local helper routes
    if (input.includes('/playlist/')) {
      const playlistEndpoints = [`/api/playlist/${uuid}`, `/api/suno/playlist/${uuid}`];
      if (canUseLocalHelper()) {
        playlistEndpoints.push(`${SoundLabAPI.LOCAL_PROXY_URL}/api/suno/playlist/${uuid}`);
      }
      for (const endpoint of playlistEndpoints) {
        try {
          const resp = await fetch(endpoint);
          if (resp.ok) {
            const data = await resp.json();
            const clips = (data.playlist_clips || []).map((item) => {
              const c = item.clip || {};
              const cid = (c.id || '').toLowerCase().trim();
              return {
                uuid: cid,
                title: c.title || `Suno_${cid.slice(0, 8)}`,
                artist: 'Suno AI',
                imageLarge: c.image_large_url || `https://cdn2.suno.ai/image_large_${cid}.jpeg`,
                imageThumb: c.image_url || `https://cdn1.suno.ai/image_${cid}.jpeg`,
                streamUrl: `/api/suno/stream/${cid}`,
                url: `https://suno.com/song/${cid}`,
                duration: c.duration || 0,
                prompt: (c.metadata || {}).prompt || '',
                tags: (c.metadata || {}).tags || 'Suno AI Track',
                platform: 'Suno AI',
                hasVideo: true,
                hasAudio: true,
                hasStem: true
              };
            });
            return {
              type: 'playlist',
              id: uuid,
              title: data.name || `Suno Playlist ${uuid.slice(0, 8)}`,
              count: clips.length,
              clips
            };
          }
        } catch (e) {}
      }
    }

    // Single Clip: Try same-origin clip proxy first, then direct Suno API
    let title = `Suno_${uuid.slice(0, 8)}`;
    let duration = 180;
    let image = `https://cdn2.suno.ai/image_large_${uuid}.jpeg`;
    let prompt = '';
    let tags = 'Suno AI Generation';

    try {
      const clipResp = await fetch(`/api/clip/${uuid}`);
      if (clipResp.ok) {
        const c = await clipResp.json();
        title = c.title || title;
        duration = c.duration || duration;
        image = c.image_large_url || image;
        prompt = (c.metadata || {}).prompt || '';
        tags = (c.metadata || {}).tags || tags;
      } else {
        const sResp = await fetch(`/api/suno/song/${uuid}`);
        if (sResp.ok) {
          const c = await sResp.json();
          title = c.title || title;
          duration = c.duration || duration;
          image = c.image_large_url || image;
          prompt = (c.metadata || {}).prompt || '';
          tags = (c.metadata || {}).tags || tags;
        } else {
          const directResp = await fetch(`https://studio-api.prod.suno.com/api/clip/${uuid}`);
          if (directResp.ok) {
            const c = await directResp.json();
            title = c.title || title;
            duration = c.duration || duration;
            image = c.image_large_url || image;
            prompt = (c.metadata || {}).prompt || '';
            tags = (c.metadata || {}).tags || tags;
          }
        }
      }
    } catch (e) {}

    return {
      type: 'single',
      uuid,
      id: uuid,
      title,
      artist: 'Suno AI',
      duration,
      imageLarge: image,
      imageThumb: image,
      streamUrl: `/api/suno/stream/${uuid}`,
      url: `https://suno.com/song/${uuid}`,
      prompt,
      tags,
      platform: 'Suno AI',
      hasVideo: true,
      hasAudio: true,
      hasStem: true
    };
  }

  /**
   * Starts a download job
   */
  static _jobOrigins = new Map();

  static async startDownload(url, targetFormat = 'mp3', audioOnly = false) {
    let response;
    try {
      response = await fetch('/api/omni/download', {
        timeoutMs: 300000,
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, format: targetFormat, is_audio_only: audioOnly })
      });
    } catch (error) {
      throw new Error('The download server connection ended before confirming the job. Check the server before retrying; the request was not replayed to another service.');
    }
    let serverFallbackMessage = '';
    // An explicit non-404/non-501 server error is authoritative; don't replay it to another service.
    if (response && response.status !== 404 && response.status !== 501) {
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || data.message || `Download server returned HTTP ${response.status}.`);
      const id = data.job_id || data.jobId;
      if (!id) throw new Error('The download server did not return a job ID.');
      SoundLabAPI._jobOrigins.set(id, ''); return id;
    }
    if (response && !response.ok) {
      const data = await response.json().catch(() => ({}));
      serverFallbackMessage = data.error || data.message || '';
    }
    if (!canUseLocalHelper()) throw new Error(serverFallbackMessage || 'This host has no download backend. Import a local file or use the desktop app.');
    let res;
    try {
      res = await fetch(`${SoundLabAPI.LOCAL_PROXY_URL}/api/omni/download`, {
        timeoutMs: 300000,
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, format: targetFormat, audioOnly, is_audio_only: audioOnly })
      });
    } catch (helperErr) {
      throw new Error(serverFallbackMessage || helperErr.message || 'The local download helper is not running.');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'The local download helper rejected this request.');
    const id = data.jobId || data.job_id;
    if (!id) throw new Error('The helper did not return a job ID.');
    SoundLabAPI._jobOrigins.set(id, SoundLabAPI.LOCAL_PROXY_URL); return id;
  }

  static async pollJob(jobId, onProgress = () => {}) {
    if (!SoundLabAPI._jobOrigins.has(jobId)) throw new Error('The job origin is unknown. Start the download again.');
    const base = SoundLabAPI._jobOrigins.get(jobId);
    const deadline = Date.now() + 5 * 60 * 1000;
    try {
      while (Date.now() < deadline) {
        const res = await fetch(`${base}/api/omni/status/${encodeURIComponent(jobId)}`, { signal: AbortSignal.timeout(Math.min(15000, deadline - Date.now())) });
        const job = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(job.error || `Download status returned HTTP ${res.status}.`);
        onProgress(job.progress ?? job.percent ?? 0, job.message || 'Processing…');
        if (['failed', 'error'].includes(job.status)) throw new Error(job.error || 'Download failed.');
        if (['completed', 'complete'].includes(job.status)) {
          return job.download_url || (base ? `${base}/api/omni/download-file/${encodeURIComponent(jobId)}` : `/api/omni/stream/${encodeURIComponent(jobId)}`);
        }
        await new Promise(resolve => setTimeout(resolve, 800));
      }
      throw new Error('Download timed out.');
    } finally { SoundLabAPI._jobOrigins.delete(jobId); }
  }

  /**
   * Saves cookies to server for private downloads
   */
  static async saveCookies(cookiesText) {
    if (!canUseLocalHelper()) throw new Error('Shared-host cookie uploads require the administrator. Keep private cookies in the local desktop/helper workflow.');
    const res = await fetch('/api/omni/cookies', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cookies: cookiesText })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || data.message || 'Cookie upload is unavailable on this server.');
    return data;
  }
}
