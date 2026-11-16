export function safeFilename(title, extension) {
  const base = String(title || 'SoundLab capture')
    .replace(/[<>:"/\\|?*\x00-\x1f]+/g, ' ')
    .replace(/\.(mp3|m4a|aac|wav|flac|ogg|opus|mp4|webm|mov|mkv|m3u8|mpd)$/i, '')
    .replace(/\s+/g, ' ').trim().replace(/[. ]+$/, '').slice(0, 120) || 'SoundLab capture';
  return `${/^(con|prn|aux|nul|com[0-9]|lpt[0-9])$/i.test(base) ? '_' : ''}${base}.${extension}`;
}

export function mediaUrl(value) {
  const url = new URL(value);
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) {
    throw new Error('Choose an HTTP or HTTPS media stream.');
  }
  return url.href;
}

export function sourceSize(headers) {
  const range = String(headers.get('content-range') || '').match(/\/(\d+)$/);
  return Number(range?.[1] || headers.get('content-length') || 0);
}

export function streamKey(url) {
  // Query parameters can select different resolutions and audio tracks.
  return mediaUrl(url);
}

export function qualityLabel(item) {
  const parts = [];
  if (item.width && item.height) parts.push(`${item.width} × ${item.height}`);
  if (item.bitrate) parts.push(`${Math.round(item.bitrate / 1000)} kbps`);
  if (item.isSegment) parts.push('Stream segment');
  return parts.join(' · ') || (item.isManifest ? 'Adaptive playlist' : 'Source quality');
}
