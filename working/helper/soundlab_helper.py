#!/usr/bin/env python3
"""
NTK SoundLab Studio - Universal Media Helper & Local Server
Features:
- Serves the frontend web app on http://127.0.0.1:8899
- Universal yt-dlp extractor for 1,000+ sites (YouTube, TikTok, SoundCloud, Instagram, Twitter/X, Vimeo, Facebook, etc.)
- Audio-only extraction (MP3 320k, WAV, M4A, FLAC) and 1080p/720p Video downloads
- Active Mango DRM proxy and direct AES-CTR/GCM decryption for Suno AI
- In-memory & disk cookie management for private and age-gated media
- Native PyTorch HTDemucs v4 multi-stem AI server (2-stem, 4-stem, lead/backing vocal demixing)
- Local FFmpeg format transcoder
"""

import sys
import os
import re
import json
import html
import ipaddress
import shutil
import socket
import base64
import hashlib
import argparse
import io
import wave
import time
import tempfile
import uuid as uuid_lib
import threading
import subprocess
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

from local_server import STUDIO_ROOT, StudioHandler, create_server

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
except ImportError:
    Cipher = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

# Active background jobs: { job_id: { status, percent, message, file_path, meta, error } }
JOBS = {}
JOBS_LOCK = threading.Lock()

MAX_COOKIE_BYTES = 64 * 1024
MAX_STEM_BYTES = 640 * 1024 * 1024
CONFIG_ROOT = (
    Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    if os.name == 'nt' else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
)
COOKIE_FILE_PATH = CONFIG_ROOT / 'NTKSoundLabStudio' / 'helper' / 'user_cookies.txt'
PREVIOUS_PRIVATE_COOKIE_FILE = CONFIG_ROOT / 'NTKOmniStreamStudio' / 'helper' / 'user_cookies.txt'
LEGACY_COOKIE_FILE = Path(__file__).resolve().with_name('user_cookies.txt')

UUID_REGEX = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
UUID_FULL_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
PLAYLIST_URL_REGEX = re.compile(r'/playlist/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', re.I)
SAFE_ID_RE = re.compile(r'[^a-zA-Z0-9_-]+')
ACE_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{6,64}$')
ACE_LOCALE_RE = re.compile(r'^[a-zA-Z]{2,5}(?:-[a-zA-Z0-9]{2,8})?$')
VOCAROO_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{6,24}$')
AUDIUS_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{3,32}$')
META_TAG_RE = re.compile(r'<meta\b[^>]*>', re.I)
HTML_ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_.:]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
AUDIO_TAG_SRC_RE = re.compile(r'<audio\b[^>]*\bsrc\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.I)
RANGE_HEADER_RE = re.compile(r'^bytes=(?:[0-9]+-[0-9]*|-[0-9]+)$')
AUDIO_STREAM_MIMES = frozenset({
    'audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/m4a', 'audio/x-m4a',
    'audio/aac', 'audio/x-aac', 'audio/aacp',
    'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/ogg', 'audio/opus',
    'audio/flac', 'audio/x-flac', 'audio/webm', 'video/mp4', 'video/webm',
    'application/ogg', 'application/octet-stream', 'binary/octet-stream',
})
IMAGE_COVER_MIMES = frozenset({'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'})
MAX_ACE_HTML_BYTES = 2 * 1024 * 1024
MAX_ACE_AUDIO_BYTES = 512 * 1024 * 1024
MAX_ACE_COVER_BYTES = 16 * 1024 * 1024

OG_AUDIO_PROVIDERS = {
    'acemusic': {
        'name': 'ACE Music',
        'page_hosts': ('acemusic.ai', 'www.acemusic.ai'),
        'cdn_hosts': (),
        'cdn_suffixes': ('.acemusic.ai', '.r2.cloudflarestorage.com', '.r2.dev'),
        'strip_suffixes': (' | ACE Music', ' - ACE Music'),
        'canonical_url': 'https://acemusic.ai/song/{id}',
    },
    'flowmusic': {
        'name': 'Flow Music',
        'page_hosts': ('flowmusic.app', 'www.flowmusic.app', 'riffusion.com', 'www.riffusion.com', 'producer.ai', 'www.producer.ai'),
        'cdn_hosts': ('storage.googleapis.com',),
        'cdn_suffixes': ('.flowmusic.app', '.riffusion.com', '.producer.ai'),
        'strip_suffixes': (' | Flow Music', ' - Flow Music', ' | Riffusion', ' - Riffusion', ' | Producer.ai', ' - Producer.ai'),
        'canonical_url': 'https://www.flowmusic.app/song/{id}',
    },
    'treblo': {
        'name': 'Treblo',
        'page_hosts': ('treblo.com', 'www.treblo.com', 'sonauto.ai', 'www.sonauto.ai'),
        'cdn_hosts': (),
        'cdn_suffixes': ('.treblo.com', '.sonauto.ai', '.r2.cloudflarestorage.com'),
        'strip_suffixes': (' | Treblo', ' - Treblo', ' | Sonauto', ' - Sonauto'),
        'canonical_url': 'https://treblo.com/song/{id}',
    },
}

DRM_PLATFORM_HOSTS = (
    ('spotify.com', 'Spotify'),
    ('music.apple.com', 'Apple Music'),
    ('itunes.apple.com', 'Apple Music'),
    ('tidal.com', 'Tidal'),
    ('deezer.com', 'Deezer'),
    ('pandora.com', 'Pandora'),
    ('boomplay.com', 'Boomplay'),
    ('audiomack.com', 'Audiomack'),
)


def sanitize_media_id(raw_id: str, fallback_seed: str = '') -> str:
    cleaned = SAFE_ID_RE.sub('-', str(raw_id or '').strip()).strip('-')[:140]
    if cleaned:
        return cleaned
    return hashlib.md5(str(fallback_seed or raw_id or 'track').encode('utf-8')).hexdigest()[:12]


def is_suno_url(url: str) -> bool:
    raw = str(url or '').strip()
    if not raw:
        return False
    if UUID_FULL_RE.match(raw):
        return True
    try:
        host = (urllib.parse.urlparse(raw).hostname or '').lower().rstrip('.')
    except ValueError:
        return False
    return host in ('suno.com', 'suno.ai') or host.endswith('.suno.com') or host.endswith('.suno.ai')


def _host_matches(host: str, domain: str) -> bool:
    h = (host or '').lower().rstrip('.')
    d = (domain or '').lower().rstrip('.')
    return bool(h and d and (h == d or h.endswith('.' + d)))


def detect_drm_platform(url: str) -> str:
    try:
        host = (urllib.parse.urlparse(str(url or '').strip()).hostname or '').lower().rstrip('.')
    except ValueError:
        return ''
    if not host:
        return ''
    if host.startswith('music.amazon.'):
        return 'Amazon Music'
    for domain, name in DRM_PLATFORM_HOSTS:
        if _host_matches(host, domain):
            return name
    return ''


def drm_platform_error(platform: str) -> str:
    if platform == 'Audiomack':
        return (
            "Audiomack uses OAuth-signed browser streams instead of public unauthenticated audio URLs. "
            "Open the track in Chrome/Edge and send it with NTK SoundLab Media Grabber, or import a "
            "local MP3/WAV/FLAC/M4A file."
        )
    return (
        f"{platform} streams are DRM-protected and require an official {platform} session/license. "
        f"SoundLab Studio cannot extract DRM-encrypted tracks from {platform}; please import a "
        "local MP3/WAV/FLAC/M4A file instead."
    )


def _is_provider_host(provider: str, host: str, allow_subdomains: bool = False) -> bool:
    cfg = OG_AUDIO_PROVIDERS.get(provider)
    if not cfg:
        return False
    h = (host or '').lower().rstrip('.')
    if h in cfg['page_hosts']:
        return True
    if not allow_subdomains:
        return False
    if h in cfg['cdn_hosts']:
        return True
    return any(h.endswith(sfx) for sfx in cfg['cdn_suffixes'])


def _is_acemusic_host(host: str, allow_subdomains: bool = False) -> bool:
    return _is_provider_host('acemusic', host, allow_subdomains)


def extract_provider_song_id(provider: str, url: str) -> str:
    cfg = OG_AUDIO_PROVIDERS.get(provider)
    if not cfg:
        return ''
    raw = str(url or '').strip()
    if ACE_ID_RE.match(raw):
        return raw
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        return ''
    if parsed.scheme.lower() != 'https' or not _is_provider_host(provider, parsed.hostname or ''):
        return ''
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) == 2 and parts[0] in ('song', 'songs') and ACE_ID_RE.match(parts[1]):
        return parts[1]
    if len(parts) == 3 and ACE_LOCALE_RE.match(parts[0]) and parts[1] in ('song', 'songs') and ACE_ID_RE.match(parts[2]):
        return parts[2]
    return ''


def detect_og_provider(url: str) -> str:
    try:
        host = (urllib.parse.urlparse(str(url or '').strip()).hostname or '').lower().rstrip('.')
    except ValueError:
        return ''
    for key in OG_AUDIO_PROVIDERS:
        if _is_provider_host(key, host) and extract_provider_song_id(key, url):
            return key
    return ''


def extract_acemusic_id(url: str) -> str:
    return extract_provider_song_id('acemusic', url)


def is_acemusic_url(url: str) -> bool:
    return detect_og_provider(url) == 'acemusic'


def is_audiomack_url(url: str) -> bool:
    return detect_drm_platform(url) == 'Audiomack'


def _assert_public_url(url: str, host_checker, label: str = 'Media'):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme.lower() != 'https' or not host or (host_checker is not None and not host_checker(host)):
        raise ValueError(f"{label} URL host or scheme is not permitted.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials in media URLs are not permitted.")
    infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    if not infos:
        raise ValueError(f"Could not resolve {label} host.")
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
            raise ValueError(f"{label} destination resolved to a non-public address.")


def _assert_public_acemusic_url(url: str, allow_subdomains: bool = False):
    _assert_public_url(
        url,
        lambda h: _is_provider_host('acemusic', h, allow_subdomains),
        'ACE Music',
    )


class _SafePublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, host_checker, label: str = 'Media'):
        super().__init__()
        self.host_checker = host_checker
        self.label = label

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        next_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if next_req is not None:
            _assert_public_url(next_req.full_url, self.host_checker, self.label)
        return next_req


def _open_public_url(url: str, host_checker=None, label: str = 'Media', extra_headers: dict | None = None, timeout: int = 20, method: str | None = None):
    _assert_public_url(url, host_checker, label)
    headers = {'User-Agent': 'NTK-SoundLab-Studio/2026.11'}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers, method=method)
    opener = urllib.request.build_opener(_SafePublicRedirectHandler(host_checker, label))
    return opener.open(req, timeout=timeout)


def _open_acemusic_url(url: str, allow_subdomains: bool = False, extra_headers: dict | None = None, timeout: int = 20):
    return _open_public_url(
        url,
        host_checker=lambda h: _is_provider_host('acemusic', h, allow_subdomains),
        label='ACE Music',
        extra_headers=extra_headers,
        timeout=timeout,
    )


def _open_provider_url(provider: str, url: str, allow_subdomains: bool = False, extra_headers: dict | None = None, timeout: int = 20):
    if provider == 'acemusic':
        return _open_acemusic_url(url, allow_subdomains=allow_subdomains, extra_headers=extra_headers, timeout=timeout)
    cfg = OG_AUDIO_PROVIDERS[provider]
    return _open_public_url(
        url,
        host_checker=lambda h: _is_provider_host(provider, h, allow_subdomains),
        label=cfg['name'],
        extra_headers=extra_headers,
        timeout=timeout,
    )


def _extract_meta_attr(html_body: str, target_key: str) -> str:
    want = target_key.lower()
    for tag in META_TAG_RE.findall(html_body):
        key = ''
        content = ''
        for attr_name, dbl, sgl in HTML_ATTR_RE.findall(tag):
            name = attr_name.lower()
            val = dbl if dbl != '' else sgl
            if name in ('property', 'name'):
                key = val.strip().lower()
            elif name == 'content':
                content = html.unescape(val.strip())
        if key == want and content:
            return content
    return ''


def _split_provider_title(raw_title: str, song_id: str, provider_name: str, strip_suffixes: tuple[str, ...]) -> tuple[str, str]:
    cleaned = (raw_title or '').strip()
    for suffix in strip_suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
    for sep in (' by ', ' par '):
        idx = cleaned.rfind(sep)
        if idx > 0:
            title = cleaned[:idx].strip()
            artist = cleaned[idx + len(sep):].strip()
            if title and artist:
                return title, artist
    fallback_id = song_id if len(song_id) <= 16 else song_id[:8]
    return (cleaned or f"{provider_name}_{fallback_id}", provider_name)


def resolve_og_provider_info(provider: str, url: str) -> tuple[dict, str, str]:
    cfg = OG_AUDIO_PROVIDERS.get(provider)
    if not cfg:
        raise ValueError("Unsupported media provider.")
    label = cfg['name']
    song_id = extract_provider_song_id(provider, url)
    if not song_id:
        raise ValueError(f"Please provide a valid {label} song link.")
    page_url = cfg['canonical_url'].format(id=song_id)
    try:
        with _open_provider_url(provider, page_url, allow_subdomains=False, timeout=20) as resp:
            ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if ctype and ctype not in ('text/html', 'application/xhtml+xml'):
                raise ValueError(f"{label} returned an unexpected response type.")
            raw_bytes = resp.read(MAX_ACE_HTML_BYTES + 1)
            if len(raw_bytes) > MAX_ACE_HTML_BYTES:
                raise ValueError(f"{label} returned an oversized song page.")
            final_url = resp.geturl() or page_url
    except urllib.error.HTTPError as exc:
        raise ValueError(f"{label} song page returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Could not reach {label}.") from exc

    body = raw_bytes.decode('utf-8', errors='replace')
    audio_raw = _extract_meta_attr(body, 'og:audio')
    if not audio_raw:
        m = AUDIO_TAG_SRC_RE.search(body)
        if m:
            audio_raw = html.unescape((m.group(1) or m.group(2) or '').strip())
    if not audio_raw:
        raise ValueError(f"{label} did not expose a public audio stream for this link.")

    audio_url = urllib.parse.urljoin(final_url, audio_raw)
    _assert_public_url(audio_url, lambda h: _is_provider_host(provider, h, True), label)

    cover_url = ''
    cover_raw = _extract_meta_attr(body, 'og:image')
    if cover_raw:
        candidate = urllib.parse.urljoin(final_url, cover_raw)
        try:
            _assert_public_url(candidate, lambda h: _is_provider_host(provider, h, True), label)
            cover_url = candidate
        except ValueError:
            cover_url = ''

    title, artist = _split_provider_title(_extract_meta_attr(body, 'og:title'), song_id, label, cfg['strip_suffixes'])
    desc = _extract_meta_attr(body, 'description') or _extract_meta_attr(body, 'og:description')
    cover_proxy = f"/api/{provider}/cover/{song_id}" if cover_url else ""
    norm_id = song_id.lower()
    meta = {
        'type': 'single',
        'uuid': f"{provider}-{norm_id}",
        'id': norm_id,
        'title': title,
        'artist': artist,
        'duration': 0,
        'imageLarge': cover_proxy,
        'imageThumb': cover_proxy,
        'streamUrl': f"/api/{provider}/stream/{song_id}",
        'url': final_url if page_url != final_url else page_url,
        'platform': label,
        'hasVideo': False,
        'hasAudio': True,
        'hasStem': True,
        'tags': f"{label} • {artist}",
        'prompt': desc,
    }
    return meta, audio_url, cover_url


def resolve_acemusic_info(url: str) -> tuple[dict, str, str]:
    return resolve_og_provider_info('acemusic', url)


def is_audius_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(str(url or '').strip()).hostname or '').lower().rstrip('.')
    except ValueError:
        return False
    return _host_matches(host, 'audius.co')


def resolve_audius_info(url: str) -> dict:
    api_url = 'https://api.audius.co/v1/resolve?url=' + urllib.parse.quote(str(url).strip(), safe='')
    try:
        with _open_public_url(api_url, lambda h: h == 'api.audius.co', 'Audius', {'Accept': 'application/json'}, timeout=15) as resp:
            payload = json.loads(resp.read(MAX_ACE_HTML_BYTES).decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Audius API returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError("Could not reach Audius API.") from exc
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Audius returned unreadable metadata.") from exc

    data = payload.get('data') if isinstance(payload, dict) else None
    if isinstance(data, list) and data:
        # Playlist or collection array
        clips = []
        for item in data:
            if isinstance(item, dict) and AUDIUS_ID_RE.match(str(item.get('id') or '')):
                clips.append(_format_audius_track(item))
        if clips:
            return {
                'type': 'playlist',
                'id': sanitize_media_id(clips[0]['id'], url),
                'title': 'Audius Playlist',
                'uploader': clips[0]['artist'],
                'count': len(clips),
                'clips': clips,
            }
    if isinstance(data, dict) and isinstance(data.get('tracks'), list):
        clips = [_format_audius_track(t) for t in data['tracks'] if isinstance(t, dict) and AUDIUS_ID_RE.match(str(t.get('id') or ''))]
        if not clips:
            raise ValueError("Audius playlist contains no streamable tracks.")
        return {
            'type': 'playlist',
            'id': sanitize_media_id(str(data.get('id') or ''), url),
            'title': data.get('playlist_name') or 'Audius Playlist',
            'uploader': (data.get('user') or {}).get('name') or 'Audius',
            'count': len(clips),
            'clips': clips,
        }
    if isinstance(data, dict) and AUDIUS_ID_RE.match(str(data.get('id') or '')):
        track = _format_audius_track(data, webpage_url=str(url).strip())
        track['type'] = 'single'
        return track
    raise ValueError("Audius did not return a playable track or playlist for this link.")


def _format_audius_track(data: dict, webpage_url: str = '') -> dict:
    tid = str(data.get('id') or '').strip()
    artist = (data.get('user') or {}).get('name') or (data.get('user') or {}).get('handle') or 'Audius Creator'
    artwork = data.get('artwork') if isinstance(data.get('artwork'), dict) else {}
    has_art = bool(artwork.get('1000x1000') or artwork.get('480x480') or artwork.get('150x150'))
    cover_proxy = f"/api/audius/cover/{tid}" if has_art else ''
    genre = data.get('genre') or 'Audius'
    return {
        'uuid': f"audius-{tid.lower()}",
        'id': tid,
        'title': data.get('title') or f"Audius_{tid}",
        'artist': artist,
        'duration': int(data.get('duration') or 0),
        'imageLarge': cover_proxy,
        'imageThumb': cover_proxy,
        'streamUrl': f"/api/audius/stream/{tid}",
        'url': webpage_url or f"https://audius.co{data.get('permalink') or ''}",
        'platform': 'Audius',
        'hasVideo': False,
        'hasAudio': True,
        'hasStem': True,
        'tags': f"Audius • {genre} • {artist}",
        'prompt': data.get('description') or '',
    }


def extract_vocaroo_id(url: str) -> str:
    raw = str(url or '').strip()
    if VOCAROO_ID_RE.match(raw):
        return raw
    try:
        parsed = urllib.parse.urlparse(raw)
    except ValueError:
        return ''
    host = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme.lower() not in ('http', 'https') or not (_host_matches(host, 'vocaroo.com') or _host_matches(host, 'voca.ro')):
        return ''
    parts = [p for p in parsed.path.split('/') if p]
    if len(parts) == 1 and VOCAROO_ID_RE.match(parts[0]):
        return parts[0]
    if len(parts) == 2 and parts[0] in ('embed', 'i') and VOCAROO_ID_RE.match(parts[1]):
        return parts[1]
    return ''


def is_vocaroo_url(url: str) -> bool:
    return bool(extract_vocaroo_id(url))


def vocaroo_media_url(vid: str) -> str:
    use_media1 = len(vid) == 10 or (len(vid) == 12 and vid.startswith('1'))
    sub = 'media1' if use_media1 else 'media'
    return f"https://{sub}.vocaroo.com/mp3/{vid}"


def resolve_vocaroo_info(url: str) -> dict:
    vid = extract_vocaroo_id(url)
    if not vid:
        raise ValueError("Please provide a valid Vocaroo recording link.")
    mp3_url = vocaroo_media_url(vid)
    host_ok = lambda h: h in ('media.vocaroo.com', 'media1.vocaroo.com')
    try:
        try:
            with _open_public_url(mp3_url, host_ok, 'Vocaroo', timeout=12, method='HEAD') as resp:
                ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        except urllib.error.HTTPError as exc:
            if exc.code == 405:
                with _open_public_url(mp3_url, host_ok, 'Vocaroo', {'Range': 'bytes=0-0'}, timeout=12) as resp:
                    ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            else:
                raise
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            raise ValueError("Vocaroo recording was not found or has expired.") from exc
        raise ValueError(f"Vocaroo returned HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise ValueError("Could not reach Vocaroo media CDN.") from exc

    if ctype and ctype not in AUDIO_STREAM_MIMES:
        raise ValueError("Vocaroo returned an unexpected media content type.")
    return {
        'type': 'single',
        'uuid': f"vocaroo-{vid.lower()}",
        'id': vid,
        'title': f"Vocaroo_{vid}",
        'artist': 'Vocaroo Voice Recording',
        'duration': 0,
        'imageLarge': '',
        'imageThumb': '',
        'streamUrl': f"/api/vocaroo/stream/{vid}",
        'url': f"https://vocaroo.com/{vid}",
        'platform': 'Vocaroo',
        'hasVideo': False,
        'hasAudio': True,
        'hasStem': True,
        'tags': 'Vocaroo • Voice Note',
    }


# =========================================================================
# UNIVERSAL MEDIA RESOLUTION & EXTRACTION VIA YT-DLP
# =========================================================================

def write_private_cookies(contents, replace=True):
    COOKIE_FILE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=COOKIE_FILE_PATH.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(contents)
        if replace:
            os.replace(temporary, COOKIE_FILE_PATH)
        else:
            os.link(temporary, COOKIE_FILE_PATH)
    except FileExistsError:
        if replace:
            raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def copy_legacy_cookies():
    if COOKIE_FILE_PATH.exists():
        return
    for source in (PREVIOUS_PRIVATE_COOKIE_FILE, LEGACY_COOKIE_FILE):
        if source.is_symlink() or not source.is_file():
            continue
        try:
            with source.open('rb') as handle:
                contents = handle.read(MAX_COOKIE_BYTES + 1)
            if len(contents) <= MAX_COOKIE_BYTES:
                write_private_cookies(contents, replace=False)
        except OSError:
            print('Could not import the previous cookie file. Open the local helper and import it again if needed.')
        return


def get_ytdl_base_opts():
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': False,
        'logtostderr': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    }
    if not COOKIE_FILE_PATH.is_symlink() and COOKIE_FILE_PATH.is_file() and COOKIE_FILE_PATH.stat().st_size > 0:
        opts['cookiefile'] = str(COOKIE_FILE_PATH)
    return opts


def _clean_ytdl_error(url: str, exc: Exception) -> ValueError:
    msg = str(exc or '').strip()
    lower = msg.lower()
    if any(k in lower for k in ('logged-in', 'login', 'sign in', 'authentication', 'cookies', 'private', 'members-only')):
        return ValueError(
            "This link requires an authenticated session or cookies. Open 'Manage Session Cookies' to import your browser cookies, or import the audio file locally."
        )
    if 'tralbum' in lower and 'bandcamp' in lower:
        return ValueError(
            "Bandcamp blocked automated track extraction or this track requires purchase. Use a free public Bandcamp track or import the downloaded audio file locally."
        )
    if "'bool' object is not subscriptable" in lower or ('unsupported url' in lower):
        return ValueError(
            f"Upstream site structure changed or is not supported by automated extraction for {url}. Try downloading/exporting the audio from the site and importing it locally."
        )
    return ValueError(msg or f"Could not extract media metadata from {url}.")


def resolve_media_info(url: str) -> dict:
    """
    Extracts universal metadata: title, uploader, duration, thumbnail, formats, audio streams.
    """
    if is_suno_url(url):
        return resolve_suno_info(url)
    og_provider = detect_og_provider(url)
    if og_provider:
        meta, _, _ = resolve_og_provider_info(og_provider, url)
        return meta
    if is_audius_url(url):
        return resolve_audius_info(url)
    if is_vocaroo_url(url):
        return resolve_vocaroo_info(url)

    drm_plat = detect_drm_platform(url)
    if drm_plat:
        raise ValueError(drm_platform_error(drm_plat))

    if not yt_dlp:
        raise RuntimeError("yt-dlp is not installed in the Python environment. Run: pip install yt-dlp")

    opts = get_ytdl_base_opts()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except ValueError:
        raise
    except Exception as exc:
        raise _clean_ytdl_error(url, exc) from exc
    if not info:
        raise ValueError(f"Could not extract info for URL: {url}")

    # Playlist vs Single Video
    if 'entries' in info and info.get('_type') == 'playlist':
        clips = []
        for entry in (info.get('entries') or []):
            if not entry:
                continue
            clips.append(_format_entry(entry))
        return {
            'type': 'playlist',
            'id': sanitize_media_id(info.get('id'), url) if info.get('id') else str(uuid_lib.uuid4())[:8],
            'title': info.get('title') or 'Playlist',
            'uploader': info.get('uploader') or info.get('channel') or '',
            'count': len(clips),
            'clips': clips
        }
    else:
        formatted = _format_entry(info)
        formatted['type'] = 'single'
        return formatted


def _format_entry(entry: dict) -> dict:
    webpage_url = entry.get('webpage_url') or entry.get('url') or ''
    cid = sanitize_media_id(entry.get('id'), webpage_url)
    duration = entry.get('duration') or 0
    title = entry.get('title') or f"Media_{cid}"
    uploader = entry.get('uploader') or entry.get('channel') or entry.get('artist') or 'Unknown Creator'
    thumbnail = entry.get('thumbnail') or ''

    # Detect platform
    extractor = (entry.get('extractor_key') or entry.get('extractor') or '').lower()
    lower_url = webpage_url.lower()
    platform = 'Universal'
    if 'youtube' in extractor: platform = 'YouTube'
    elif 'tiktok' in extractor: platform = 'TikTok'
    elif 'soundcloud' in extractor: platform = 'SoundCloud'
    elif 'audiomack' in extractor: platform = 'Audiomack'
    elif 'acemusic' in extractor or 'acemusic.ai' in lower_url: platform = 'ACE Music'
    elif 'flowmusic.app' in lower_url or 'riffusion.com' in lower_url or 'producer.ai' in lower_url: platform = 'Flow Music'
    elif 'treblo.com' in lower_url or 'sonauto.ai' in lower_url: platform = 'Treblo'
    elif 'audius' in extractor or 'audius.co' in lower_url: platform = 'Audius'
    elif 'vocaroo' in extractor or 'vocaroo.com' in lower_url or 'voca.ro' in lower_url: platform = 'Vocaroo'
    elif 'mixcloud' in extractor or 'mixcloud.com' in lower_url: platform = 'Mixcloud'
    elif 'freesound' in extractor or 'freesound.org' in lower_url: platform = 'Freesound'
    elif 'jamendo' in extractor or 'jamendo.com' in lower_url: platform = 'Jamendo'
    elif 'bandcamp' in extractor or 'bandcamp.com' in lower_url: platform = 'Bandcamp'
    elif 'archive' in extractor or 'archive.org' in lower_url: platform = 'Internet Archive'
    elif 'dailymotion' in extractor: platform = 'Dailymotion'
    elif 'twitch' in extractor: platform = 'Twitch'
    elif 'bilibili' in extractor: platform = 'Bilibili'
    elif 'reddit' in extractor: platform = 'Reddit'
    elif 'rumble' in extractor: platform = 'Rumble'
    elif 'loom' in extractor: platform = 'Loom'
    elif 'instagram' in extractor: platform = 'Instagram'
    elif 'twitter' in extractor or 'x' == extractor: platform = 'Twitter/X'
    elif 'facebook' in extractor: platform = 'Facebook'
    elif 'vimeo' in extractor: platform = 'Vimeo'

    formats_list = []
    raw_formats = entry.get('formats') or []
    has_video = False
    has_audio = False

    for f in raw_formats:
        vcodec = f.get('vcodec') or 'none'
        acodec = f.get('acodec') or 'none'
        height = f.get('height') or 0
        ext = f.get('ext') or ''
        filesize = f.get('filesize') or f.get('filesize_approx') or 0

        if vcodec != 'none': has_video = True
        if acodec != 'none': has_audio = True

        if height and height >= 360:
            formats_list.append({
                'formatId': f.get('format_id'),
                'label': f"{height}p ({ext.upper()})",
                'height': height,
                'ext': ext,
                'filesize': filesize
            })

    # Single-stream extractors (e.g. Audius, Vocaroo, Freesound fallback) populate top-level 'url' with empty 'formats'
    if entry.get('url'):
        top_v = entry.get('vcodec') or 'none'
        top_a = entry.get('acodec') or ''
        top_ext = (entry.get('ext') or '').lower()
        if top_v != 'none':
            has_video = True
        if top_a != 'none' and (top_a or top_ext in ('mp3', 'm4a', 'wav', 'flac', 'ogg', 'opus', 'aac', 'webm', 'mp4')):
            has_audio = True

    # Deduplicate video formats
    seen_heights = set()
    deduped_formats = []
    for f in sorted(formats_list, key=lambda x: x['height'], reverse=True):
        if f['height'] not in seen_heights:
            seen_heights.add(f['height'])
            deduped_formats.append(f)

    return {
        'uuid': f"omni-{cid}",
        'id': cid,
        'title': title,
        'artist': uploader,
        'duration': duration,
        'imageLarge': thumbnail,
        'imageThumb': thumbnail,
        'url': webpage_url,
        'platform': platform,
        'hasVideo': has_video,
        'hasAudio': has_audio,
        'formats': deduped_formats[:6],
        'tags': f"{platform} • {uploader}",
        'hasStem': True,
        'playerMode': 'custom'
    }


def _download_direct_provider_stream(url: str, output_dir: str, target_format: str, audio_only: bool, job_id: str) -> str | None:
    og_provider = detect_og_provider(url)
    audio_url = ''
    host_checker = None
    title_hint = 'Track'
    tid_hint = 'media'
    default_ext = 'm4a'

    if og_provider:
        meta, audio_url, _ = resolve_og_provider_info(og_provider, url)
        host_checker = lambda h: _is_provider_host(og_provider, h, True)
        title_hint = meta.get('title') or title_hint
        tid_hint = meta.get('id') or tid_hint
        path_ext = os.path.splitext(urllib.parse.urlparse(audio_url).path)[1].lstrip('.').lower()
        if path_ext in ('mp3', 'm4a', 'wav', 'ogg', 'opus', 'aac', 'flac', 'webm'):
            default_ext = path_ext
    elif is_audius_url(url):
        meta = resolve_audius_info(url)
        if meta.get('type') == 'playlist':
            return None
        tid_hint = meta.get('id') or tid_hint
        title_hint = meta.get('title') or title_hint
        audio_url = f"https://api.audius.co/v1/tracks/{tid_hint}/stream"
        default_ext = 'mp3'
    elif is_vocaroo_url(url):
        vid = extract_vocaroo_id(url)
        meta = resolve_vocaroo_info(url)
        tid_hint = vid
        title_hint = meta.get('title') or title_hint
        audio_url = vocaroo_media_url(vid)
        host_checker = lambda h: h in ('media.vocaroo.com', 'media1.vocaroo.com')
        default_ext = 'mp3'
    else:
        return None

    safe_title = re.sub(r'[^a-zA-Z0-9._-]+', '_', title_hint).strip('_')[:80] or 'Track'
    safe_tid = sanitize_media_id(tid_hint)
    raw_path = os.path.join(output_dir, f"{safe_title}_{safe_tid}.{default_ext}")
    with _open_public_url(audio_url, host_checker, 'Media CDN', timeout=60) as resp, open(raw_path, 'wb') as out:
        total = int(resp.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total > 0:
                with JOBS_LOCK:
                    JOBS[job_id]['percent'] = min(88, 10 + int((done / total) * 75))

    want_ext = target_format if (audio_only or target_format in ('mp3', 'wav', 'flac', 'm4a', 'opus', 'aac')) else default_ext
    if want_ext in ('mp3', 'wav', 'flac', 'm4a', 'opus', 'aac') and want_ext != default_ext and shutil.which('ffmpeg'):
        conv_path = os.path.join(output_dir, f"{safe_title}_{safe_tid}.{want_ext}")
        res = subprocess.run(['ffmpeg', '-y', '-i', raw_path, conv_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
        if res.returncode == 0 and os.path.isfile(conv_path):
            try:
                os.remove(raw_path)
            except OSError:
                pass
            return conv_path
    return raw_path


def download_media_task(job_id: str, url: str, target_format: str = 'mp3', audio_only: bool = False, output_dir: str = "."):
    os.makedirs(output_dir, exist_ok=True)
    with JOBS_LOCK:
        JOBS[job_id] = {
            'status': 'downloading',
            'percent': 5,
            'message': 'Starting stream download...',
            'filePath': None,
            'error': None
        }

    def ytdl_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes') or 0
            pct = 10
            if total > 0:
                pct = int(10 + (downloaded / total) * 75)
            spd = d.get('speed') or 0
            spd_mb = f"{spd / 1024 / 1024:.1f} MB/s" if spd else ""
            with JOBS_LOCK:
                JOBS[job_id]['percent'] = min(88, pct)
                JOBS[job_id]['message'] = f"Downloading stream {spd_mb}..."
        elif d['status'] == 'finished':
            with JOBS_LOCK:
                JOBS[job_id]['percent'] = 90
                JOBS[job_id]['message'] = 'Processing and packaging media...'

    try:
        drm_plat = detect_drm_platform(url)
        if drm_plat:
            raise ValueError(drm_platform_error(drm_plat))

        direct_file = _download_direct_provider_stream(url, output_dir, target_format, audio_only, job_id)
        if direct_file:
            with JOBS_LOCK:
                JOBS[job_id]['status'] = 'complete'
                JOBS[job_id]['percent'] = 100
                JOBS[job_id]['message'] = 'Download complete!'
                JOBS[job_id]['filePath'] = direct_file
            return

        if not yt_dlp:
            raise RuntimeError("yt-dlp is required to download streams from this platform.")

        base_opts = get_ytdl_base_opts()
        base_opts['progress_hooks'] = [ytdl_hook]
        out_tmpl = os.path.join(output_dir, f"%(title)s_%(id)s.%(ext)s")
        base_opts['outtmpl'] = out_tmpl

        has_ffmpeg = shutil.which('ffmpeg') is not None
        if audio_only or target_format in ['mp3', 'wav', 'flac', 'm4a', 'aac', 'ogg', 'opus']:
            base_opts['format'] = 'bestaudio/best'
            if has_ffmpeg:
                base_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': target_format if target_format in ['mp3', 'wav', 'flac', 'm4a', 'opus'] else 'mp3',
                    'preferredquality': '320' if target_format == 'mp3' else None
                }]
        else:
            # Video download (1080p, 720p, or best MP4)
            if has_ffmpeg:
                if target_format == '1080p':
                    base_opts['format'] = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
                elif target_format == '720p':
                    base_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
                else:
                    base_opts['format'] = 'bestvideo+bestaudio/best'
                base_opts['merge_output_format'] = 'mp4'
            else:
                if target_format == '720p':
                    base_opts['format'] = 'best[height<=720]/best'
                else:
                    base_opts['format'] = 'best[ext=mp4]/best'

        with yt_dlp.YoutubeDL(base_opts) as ydl:
            res = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(res)
            # Check target extension after FFmpeg post-processing
            if has_ffmpeg and (audio_only or target_format in ['mp3', 'wav', 'flac', 'm4a', 'opus']):
                base_name = os.path.splitext(filename)[0]
                expected = f"{base_name}.{target_format}"
                if os.path.isfile(expected):
                    filename = expected
            elif not os.path.isfile(filename):
                req_dl = (res or {}).get('requested_downloads') or []
                if req_dl and isinstance(req_dl[0], dict) and req_dl[0].get('filepath') and os.path.isfile(req_dl[0]['filepath']):
                    filename = req_dl[0]['filepath']

        with JOBS_LOCK:
            JOBS[job_id]['status'] = 'complete'
            JOBS[job_id]['percent'] = 100
            JOBS[job_id]['message'] = 'Download and conversion complete!'
            JOBS[job_id]['filePath'] = filename

    except Exception as exc:
        clean_err = _clean_ytdl_error(url, exc) if not isinstance(exc, ValueError) else exc
        with JOBS_LOCK:
            JOBS[job_id]['status'] = 'error'
            JOBS[job_id]['error'] = str(clean_err)
            JOBS[job_id]['message'] = f"Download failed: {clean_err}"


# =========================================================================
# SUNO AI STREAM RESOLUTION & AES DECRYPTION
# =========================================================================

def resolve_suno_info(url: str) -> dict:
    match = UUID_REGEX.search(url)
    if not match:
        raise ValueError(f"Could not find valid Suno UUID in: {url}")
    clean_uuid = match.group(0).lower()

    if '/playlist/' in url.lower():
        api_url = f"https://studio-api.prod.suno.com/api/playlist/{clean_uuid}/?page=1"
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            clips = []
            for item in data.get('playlist_clips', []):
                c = item.get('clip') or {}
                cid = (c.get('id') or '').lower().strip()
                if cid:
                    clips.append({
                        'uuid': cid,
                        'title': c.get('title') or f"Suno_{cid[:8]}",
                        'artist': 'Suno AI',
                        'duration': c.get('duration') or 0,
                        'imageLarge': c.get('image_large_url') or f"https://cdn2.suno.ai/image_large_{cid}.jpeg",
                        'imageThumb': c.get('image_url') or f"https://cdn1.suno.ai/image_{cid}.jpeg",
                        'streamUrl': f"https://d2lwuy8qc234o3.cloudfront.net/1/clip/{cid}.m4a",
                        'url': f"https://suno.com/song/{cid}",
                        'platform': 'Suno AI',
                        'hasVideo': True,
                        'hasAudio': True,
                        'hasStem': True,
                        'tags': (c.get('metadata') or {}).get('tags') or 'Suno AI Generation'
                    })
            return {
                'type': 'playlist',
                'id': clean_uuid,
                'title': data.get('name') or f"Suno Playlist {clean_uuid[:8]}",
                'uploader': 'Suno AI',
                'count': len(clips),
                'clips': clips
            }
    else:
        api_url = f"https://studio-api.prod.suno.com/api/clip/{clean_uuid}"
        title = f"Suno_{clean_uuid[:8]}"
        duration = 180
        image = f"https://cdn2.suno.ai/image_large_{clean_uuid}.jpeg"
        tags = 'Suno AI Master'
        try:
            req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                title = data.get('title') or title
                duration = data.get('duration') or duration
                image = data.get('image_large_url') or image
                tags = (data.get('metadata') or {}).get('tags') or tags
        except Exception:
            pass

        return {
            'type': 'single',
            'uuid': clean_uuid,
            'id': clean_uuid,
            'title': title,
            'artist': 'Suno AI',
            'duration': duration,
            'imageLarge': image,
            'imageThumb': image,
            'streamUrl': f"https://d2lwuy8qc234o3.cloudfront.net/1/clip/{clean_uuid}.m4a",
            'url': f"https://suno.com/song/{clean_uuid}",
            'platform': 'Suno AI',
            'hasVideo': True,
            'hasAudio': True,
            'hasStem': True,
            'tags': tags,
            'formats': [{'formatId': 'm4a', 'label': 'Lossless M4A Master', 'ext': 'm4a'}]
        }


def decrypt_suno_stream(uuid: str) -> bytes:
    if not Cipher:
        raise RuntimeError("Cryptography package required. Run: pip install cryptography")

    rights_url = "https://studio-api.prod.suno.com/api/mango/rights"
    payload = json.dumps({'clip_id': uuid}).encode('utf-8')
    req = urllib.request.Request(
        rights_url,
        data=payload,
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        rights = json.loads(resp.read().decode('utf-8'))

    wrapped = base64.b64decode(rights['wrapped_content_key'])
    iv_gcm = base64.b64decode(rights['key_wrap_iv'])
    tag_gcm = base64.b64decode(rights['key_wrap_tag'])
    app_key = bytes([
        0x3c, 0xa1, 0x9f, 0x4e, 0x2b, 0x78, 0x5d, 0x12,
        0x89, 0x4f, 0xc6, 0x23, 0x71, 0x05, 0xe8, 0x9a,
        0xd4, 0x1b, 0x6e, 0x3f, 0x90, 0x52, 0x87, 0x4c,
        0x13, 0x68, 0x29, 0xfa, 0xeb, 0x47, 0x0d, 0x51
    ])

    decryptor_gcm = Cipher(
        algorithms.AES(app_key),
        modes.GCM(iv_gcm, tag_gcm),
        backend=default_backend()
    ).decryptor()
    content_key = decryptor_gcm.update(wrapped) + decryptor_gcm.finalize()

    stream_url = f"https://d2lwuy8qc234o3.cloudfront.net/1/clip/{uuid}.m4a"
    sreq = urllib.request.Request(stream_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(sreq, timeout=30) as sresp:
        encrypted_bytes = sresp.read()

    cipher_ctr = Cipher(
        algorithms.AES(content_key),
        modes.CTR(b'\x00' * 16),
        backend=default_backend()
    )
    decryptor_ctr = cipher_ctr.decryptor()
    return decryptor_ctr.update(encrypted_bytes) + decryptor_ctr.finalize()


# =========================================================================
# NATIVE PYTORCH HTDEMUCS v4 STEM SEPARATION
# =========================================================================

# NEURAL 4-STEM SEPARATION ENGINE (META HTDEMUCS V4)
# =====================================================================

_DEMUCS_LOCK = threading.Lock()
_DEMUCS_MODEL = None
_DEMUCS_DEVICE = "cpu"
_STEM_JOBS = {}  # job_id -> dict(status, progress, stage, stems, error, created_at)


def check_demucs_available() -> dict:
    try:
        import torch
        import demucs  # noqa: F401
        import numpy  # noqa: F401
        device = "cuda" if torch.cuda.is_available() else "cpu"
        return {
            "available": True,
            "engine": "htdemucs-v4",
            "device": device,
            "stems": ["vocals", "drums", "bass", "other", "lead_vocals", "backing_vocals"],
            "supports_vocal_split": True
        }
    except Exception as exc:
        return {
            "available": False,
            "engine": "none",
            "device": "none",
            "error": str(exc),
            "supports_vocal_split": False
        }


def get_demucs_model():
    global _DEMUCS_MODEL, _DEMUCS_DEVICE
    with _DEMUCS_LOCK:
        if _DEMUCS_MODEL is None:
            import torch
            from demucs.pretrained import get_model
            _DEMUCS_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
            model = get_model("htdemucs")
            model.to(_DEMUCS_DEVICE)
            model.eval()
            _DEMUCS_MODEL = model
        return _DEMUCS_MODEL, _DEMUCS_DEVICE


def decode_wav_bytes_to_stereo_float32(wav_bytes: bytes):
    """Decodes 16-bit/24-bit/32-bit PCM WAV bytes into float32 numpy array (2, N) and sample_rate."""
    import numpy as np
    from scipy.io import wavfile

    sr, data = wavfile.read(io.BytesIO(wav_bytes))
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        audio = (data.astype(np.float32) - 128.0) / 128.0
    else:
        audio = data.astype(np.float32)

    if audio.ndim == 1:
        audio = np.stack([audio, audio], axis=0)
    else:
        # Take first 2 channels and transpose (N, C) -> (2, N)
        if audio.shape[1] == 1:
            audio = np.concatenate([audio, audio], axis=1)
        audio = audio[:, :2].T

    return sr, np.ascontiguousarray(audio, dtype=np.float32)


def encode_stereo_float32_to_wav_bytes(stereo_arr, sample_rate: int = 44100) -> bytes:
    """Encodes (2, N) float32 array in [-1, 1] into 16-bit PCM RIFF WAV bytes."""
    import numpy as np
    clipped = np.clip(stereo_arr.T, -1.0, 1.0)
    pcm16 = (clipped * 32767.0).astype(np.int16)
    out_io = io.BytesIO()
    with wave.open(out_io, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return out_io.getvalue()


def split_lead_and_backing_vocals(vocal_audio_np, sample_rate: int = 44100):
    """Separates stereo vocal array into Lead Vocals and Backing Harmonies using spectral center-extraction."""
    import numpy as np
    from scipy import signal

    left = vocal_audio_np[0]
    right = vocal_audio_np[1]
    n_samples = len(left)

    nperseg = 2048
    noverlap = 1536

    _, _, Zxx_L = signal.stft(left, fs=sample_rate, nperseg=nperseg, noverlap=noverlap)
    _, _, Zxx_R = signal.stft(right, fs=sample_rate, nperseg=nperseg, noverlap=noverlap)

    mag_L = np.abs(Zxx_L)
    mag_R = np.abs(Zxx_R)
    phase_L = np.angle(Zxx_L)
    phase_R = np.angle(Zxx_R)

    delta_phase = np.abs(phase_L - phase_R)
    coherence = np.clip(np.cos(delta_phase), 0.0, 1.0)
    center_mag = np.minimum(mag_L, mag_R) * coherence

    denom = np.maximum(mag_L, mag_R) + 1e-8
    lead_mask = np.clip(center_mag / denom, 0.0, 1.0) ** 1.35

    lead_spec_L = mag_L * lead_mask * np.exp(1j * phase_L)
    lead_spec_R = mag_R * lead_mask * np.exp(1j * phase_R)

    _, lead_L = signal.istft(lead_spec_L, fs=sample_rate, nperseg=nperseg, noverlap=noverlap)
    _, lead_R = signal.istft(lead_spec_R, fs=sample_rate, nperseg=nperseg, noverlap=noverlap)

    lead_L = lead_L[:n_samples]
    lead_R = lead_R[:n_samples]
    if len(lead_L) < n_samples:
        lead_L = np.pad(lead_L, (0, n_samples - len(lead_L)))
        lead_R = np.pad(lead_R, (0, n_samples - len(lead_R)))

    back_L = left - lead_L
    back_R = right - lead_R

    lead_stereo = np.stack([lead_L, lead_R], axis=0).astype(np.float32)
    back_stereo = np.stack([back_L, back_R], axis=0).astype(np.float32)

    return lead_stereo, back_stereo


def _prune_old_stem_jobs(max_jobs: int = 3):
    if len(_STEM_JOBS) <= max_jobs:
        return
    sorted_ids = sorted(_STEM_JOBS.keys(), key=lambda jid: _STEM_JOBS[jid].get("created_at", 0))
    for old_id in sorted_ids[:-max_jobs]:
        _STEM_JOBS.pop(old_id, None)


def _run_demucs_job(job_id: str, wav_bytes: bytes):
    job = _STEM_JOBS.get(job_id)
    if not job:
        return

    try:
        import numpy as np
        import torch
        from scipy import signal
        from demucs.apply import apply_model

        job["stage"] = "Loading Meta HTDemucs v4 neural network..."
        job["progress"] = 4
        model, device = get_demucs_model()
        target_sr = int(getattr(model, "samplerate", 44100))

        job["stage"] = "Decoding & standardizing stereo waveform..."
        job["progress"] = 8
        sr, audio_np = decode_wav_bytes_to_stereo_float32(wav_bytes)

        if sr != target_sr:
            num_target = max(1, int(round(audio_np.shape[1] * target_sr / float(sr))))
            audio_np = signal.resample(audio_np, num_target, axis=1).astype(np.float32)

        total_samples = max(1, audio_np.shape[1])
        seg_samples = int(7.8 * target_sr)

        wav_tensor = torch.from_numpy(audio_np).to(device)
        ref = wav_tensor.mean(0)
        ref_mean = ref.mean()
        ref_std = ref.std() + 1e-8
        wav_norm = (wav_tensor - ref_mean) / ref_std

        job["stage"] = f"Separating 4 neural stems on {device.upper()}..."
        job["progress"] = 12

        def on_demucs_progress(info: dict):
            offset = int(info.get("segment_offset", 0))
            state = info.get("state", "start")
            done_samples = offset + (seg_samples if state == "end" else int(seg_samples * 0.35))
            ratio = min(1.0, max(0.0, done_samples / float(total_samples)))
            pct = min(94, 12 + int(ratio * 82))
            if pct > job["progress"]:
                job["progress"] = pct
                sec_done = min(total_samples, done_samples) / float(target_sr)
                sec_tot = total_samples / float(target_sr)
                job["stage"] = f"HTDemucs neural pass: {sec_done:.0f}s / {sec_tot:.0f}s ({pct}%)"

        with torch.no_grad():
            out_sources = apply_model(
                model,
                wav_norm[None],
                shifts=0,
                split=True,
                overlap=0.25,
                progress=False,
                device=device,
                callback=on_demucs_progress
            )[0]
            out_sources = out_sources * ref_std + ref_mean

        job["stage"] = "Encoding isolated 16-bit studio WAV stems..."
        job["progress"] = 96

        source_names = list(getattr(model, "sources", ["drums", "bass", "other", "vocals"]))
        stems_wav = {}
        out_np = out_sources.detach().cpu().numpy()

        for idx, name in enumerate(source_names):
            stems_wav[name] = encode_stereo_float32_to_wav_bytes(out_np[idx], target_sr)
            if name == "vocals":
                try:
                    lead_arr, back_arr = split_lead_and_backing_vocals(out_np[idx], target_sr)
                    stems_wav["lead_vocals"] = encode_stereo_float32_to_wav_bytes(lead_arr, target_sr)
                    stems_wav["backing_vocals"] = encode_stereo_float32_to_wav_bytes(back_arr, target_sr)
                except Exception as split_err:
                    print(f"[!] Vocal demixing note: {split_err}")

        job["stems"] = stems_wav
        job["progress"] = 100
        job["stage"] = "6-Stem Neural Separation Complete (with Lead & Harmonies)!"
        job["status"] = "done"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        job["stage"] = f"Stem separation error: {exc}"


class SoundLabHTTPHandler(StudioHandler):
    def _stream_validated_upstream(self, target: str, host_checker, label: str, is_cover: bool = False, opener=None):
        req_headers = {}
        range_hdr = self.headers.get('Range')
        if range_hdr:
            if not RANGE_HEADER_RE.match(range_hdr):
                self._send_json(400, {'error': 'Only a single byte range is supported.'})
                return
            req_headers['Range'] = range_hdr
        allowed_mimes = IMAGE_COVER_MIMES if is_cover else AUDIO_STREAM_MIMES
        max_bytes = MAX_ACE_COVER_BYTES if is_cover else MAX_ACE_AUDIO_BYTES
        ctx = opener(target, req_headers) if opener is not None else _open_public_url(target, host_checker, label, extra_headers=req_headers, timeout=30)
        with ctx as resp:
            ctype = (resp.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            if ctype not in allowed_mimes:
                self._send_json(502, {'error': f'{label} returned an unexpected media content type.'})
                return
            clen = resp.headers.get('Content-Length')
            if clen and clen.isdigit() and int(clen) > max_bytes:
                self._send_json(502, {'error': 'Media exceeds helper streaming limit.'})
                return
            status = getattr(resp, 'status', 200) or 200
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            for hdr in ('Content-Length', 'Content-Range', 'Accept-Ranges'):
                val = resp.headers.get(hdr)
                if val:
                    self.send_header(hdr, val)
            self.end_headers()
            if self.command != 'HEAD':
                remaining = max_bytes
                while remaining > 0:
                    chunk = resp.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def handle_api_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 0. API: Stems Capabilities & Status
        if path == '/api/stems/capabilities':
            self._send_json(200, check_demucs_available())
            return

        if path.startswith('/api/stems/status/'):
            job_id = path.split('/api/stems/status/', 1)[1].strip('/')
            job = _STEM_JOBS.get(job_id)
            if not job:
                self._send_json(404, {'error': 'Job not found'})
                return
            self._send_json(200, {
                'job_id': job_id,
                'status': job['status'],
                'progress': job['progress'],
                'stage': job['stage'],
                'error': job['error'],
                'stems': list(job['stems'].keys()) if job['stems'] else []
            })
            return

        if path.startswith('/api/stems/download/'):
            parts = path.split('/api/stems/download/', 1)[1].strip('/').split('/')
            if len(parts) == 2:
                job_id, stem_name = parts[0], parts[1].lower()
                job = _STEM_JOBS.get(job_id)
                if job and job.get('stems') and stem_name in job['stems']:
                    wav_data = job['stems'][stem_name]
                    self.send_response(200)
                    self.send_header('Content-Type', 'audio/wav')
                    self.send_header('Content-Length', str(len(wav_data)))
                    self.end_headers()
                    self.wfile.write(wav_data)
                    return
            self._send_json(404, {'error': 'Stem audio not found'})
            return


        # 1. API: Check capabilities & health
        if path in ('/api/capabilities', '/api/health'):
            caps = {
                'status': 'ok',
                'server': 'NTK SoundLab Studio Helper v2026.5',
                'yt_dlp': bool(yt_dlp),
                'ffmpeg': self._check_ffmpeg(),
                'demucs': check_demucs_available()
            }
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(caps).encode('utf-8'))
            return

        # 2. API: Resolve stream metadata
        if path.startswith('/api/omni/resolve'):
            query = urllib.parse.parse_qs(parsed.query)
            target_url = query.get('url', [''])[0].strip()
            if not target_url:
                self._send_json(400, {'error': "Missing 'url' query parameter."})
                return
            try:
                og_provider = detect_og_provider(target_url)
                if og_provider:
                    info, _, cover_url = resolve_og_provider_info(og_provider, target_url)
                    if self.trusted_origin and cover_url:
                        info['imageLarge'] = cover_url
                        info['imageThumb'] = cover_url
                else:
                    info = resolve_media_info(target_url)
                self._send_json(200, info)
            except ValueError as e:
                self._send_json(422, {'error': str(e)})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
            return

        if path == '/api/omni/direct-stream':
            query = urllib.parse.parse_qs(parsed.query)
            target_url = query.get('url', [''])[0].strip()
            if not target_url:
                self._send_json(400, {'error': "Missing 'url' query parameter."})
                return
            try:
                # Validate scheme (http/https) and disallow private IPs on all hosts & redirects
                parsed_t = urllib.parse.urlparse(target_url)
                if parsed_t.scheme.lower() not in ('http', 'https') or not parsed_t.hostname or parsed_t.username or parsed_t.password:
                    raise ValueError("Direct media URL scheme or host is not permitted.")
                def _public_only(host, port=None):
                    infos = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
                    for i in infos:
                        addr = ipaddress.ip_address(i[4][0])
                        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved or addr.is_unspecified:
                            return False
                    return bool(infos)
                req_headers = {}
                range_hdr = self.headers.get('Range')
                if range_hdr:
                    if not RANGE_HEADER_RE.match(range_hdr):
                        self._send_json(400, {'error': 'Only a single byte range is supported.'})
                        return
                    req_headers['Range'] = range_hdr
                if not _public_only(parsed_t.hostname, parsed_t.port or (443 if parsed_t.scheme.lower() == 'https' else 80)):
                    raise ValueError("Direct media destination resolved to a non-public address.")
                class _AnyPublicRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, req, fp, code, msg, headers, newurl):
                        nr = super().redirect_request(req, fp, code, msg, headers, newurl)
                        if nr is not None:
                            p2 = urllib.parse.urlparse(nr.full_url)
                            if p2.scheme.lower() not in ('http', 'https') or not p2.hostname or not _public_only(p2.hostname, p2.port or (443 if p2.scheme.lower() == 'https' else 80)):
                                raise ValueError("Direct media redirect resolved to a disallowed host.")
                        return nr
                req = urllib.request.Request(target_url, headers={'User-Agent': 'NTK-SoundLab-Studio/2026.11', **req_headers})
                opener = urllib.request.build_opener(_AnyPublicRedirect())
                self._stream_validated_upstream(target_url, None, 'Direct Media', is_cover=False, opener=lambda _u, _h: opener.open(req, timeout=30))
            except urllib.error.HTTPError as exc:
                self._send_json(exc.code if 400 <= exc.code < 600 else 502, {'error': f'Direct media host returned HTTP {exc.code}.'})
            except ValueError as exc:
                self._send_json(422, {'error': str(exc)})
            except Exception:
                self._send_json(502, {'error': 'Could not reach remote media URL.'})
            return

        # Provider Stream & Cover Proxies (ACE Music, Flow Music, Treblo)
        matched_provider = ''
        is_cover = False
        prefix = ''
        for prov_key in OG_AUDIO_PROVIDERS:
            if path.startswith(f'/api/{prov_key}/stream/'):
                matched_provider = prov_key
                prefix = f'/api/{prov_key}/stream/'
                break
            if path.startswith(f'/api/{prov_key}/cover/'):
                matched_provider = prov_key
                is_cover = True
                prefix = f'/api/{prov_key}/cover/'
                break

        if matched_provider:
            cfg = OG_AUDIO_PROVIDERS[matched_provider]
            label = cfg['name']
            song_id = path[len(prefix):].strip('/')
            for ext in ('.mp3', '.m4a', '.wav', '.ogg', '.opus', '.aac', '.flac', '.webm', '.jpg', '.jpeg', '.png', '.webp'):
                if song_id.endswith(ext):
                    song_id = song_id[:-len(ext)]
                    break
            if not ACE_ID_RE.match(song_id):
                self._send_json(400, {'error': f'A valid {label} song ID is required.'})
                return
            try:
                _, audio_url, cover_url = resolve_og_provider_info(matched_provider, song_id)
                target = cover_url if is_cover else audio_url
                if not target:
                    self._send_json(404, {'error': f'No cover artwork is available for this {label} track.'})
                    return
                opener = (
                    (lambda tgt, hdrs: _open_acemusic_url(tgt, allow_subdomains=True, extra_headers=hdrs, timeout=30))
                    if matched_provider == 'acemusic'
                    else None
                )
                self._stream_validated_upstream(
                    target,
                    lambda h, pk=matched_provider: _is_provider_host(pk, h, True),
                    label,
                    is_cover=is_cover,
                    opener=opener,
                )
            except urllib.error.HTTPError as exc:
                self._send_json(exc.code if 400 <= exc.code < 600 else 502, {'error': f'Audio provider could not supply this track (HTTP {exc.code}).'})
            except ValueError as exc:
                self._send_json(422, {'error': str(exc)})
            except Exception:
                self._send_json(502, {'error': f'Could not reach {label}.'})
            return

        if path.startswith('/api/audius/stream/') or path.startswith('/api/audius/cover/'):
            is_cover = path.startswith('/api/audius/cover/')
            prefix = '/api/audius/cover/' if is_cover else '/api/audius/stream/'
            tid = path[len(prefix):].strip('/')
            for ext in ('.mp3', '.m4a', '.jpg', '.jpeg', '.png', '.webp'):
                if tid.endswith(ext):
                    tid = tid[:-len(ext)]
                    break
            if not AUDIUS_ID_RE.match(tid):
                self._send_json(400, {'error': 'A valid Audius track ID is required.'})
                return
            try:
                if is_cover:
                    with _open_public_url(f'https://api.audius.co/v1/tracks/{tid}', lambda h: h == 'api.audius.co', 'Audius', {'Accept': 'application/json'}, timeout=15) as resp:
                        d = (json.loads(resp.read(MAX_ACE_HTML_BYTES).decode('utf-8')) or {}).get('data') or {}
                    art = d.get('artwork') if isinstance(d.get('artwork'), dict) else {}
                    target = art.get('1000x1000') or art.get('480x480') or art.get('150x150') or ''
                    if not target:
                        self._send_json(404, {'error': 'No Audius cover artwork available.'})
                        return
                    parsed_art = urllib.parse.urlparse(target)
                    suffix = parsed_art.path + (f'?{parsed_art.query}' if parsed_art.query else '')
                    candidates = [target]
                    for mirror in (art.get('mirrors') or []):
                        mp = urllib.parse.urlparse(str(mirror or '').strip())
                        if mp.scheme == 'https' and mp.netloc:
                            alt = f'https://{mp.netloc}{suffix}'
                            if alt not in candidates:
                                candidates.append(alt)
                            if len(candidates) >= 4:
                                break
                    last_exc = None
                    for idx, cand in enumerate(candidates):
                        try:
                            if idx > 0 or len(candidates) > 1:
                                with _open_public_url(cand, None, 'Audius', method='HEAD', timeout=8):
                                    pass
                            self._stream_validated_upstream(cand, None, 'Audius', is_cover=True)
                            return
                        except Exception as cand_exc:
                            last_exc = cand_exc
                    raise last_exc
                target = f'https://api.audius.co/v1/tracks/{tid}/stream'
                self._stream_validated_upstream(target, None, 'Audius', is_cover=False)
            except urllib.error.HTTPError as exc:
                self._send_json(exc.code if 400 <= exc.code < 600 else 502, {'error': f'Audius returned HTTP {exc.code}.'})
            except ValueError as exc:
                self._send_json(422, {'error': str(exc)})
            except Exception:
                self._send_json(502, {'error': 'Could not reach Audius stream node.'})
            return

        if path.startswith('/api/vocaroo/stream/'):
            vid = path[len('/api/vocaroo/stream/'):].strip('/')
            for ext in ('.mp3', '.ogg'):
                if vid.endswith(ext):
                    vid = vid[:-len(ext)]
                    break
            if not VOCAROO_ID_RE.match(vid):
                self._send_json(400, {'error': 'A valid Vocaroo ID is required.'})
                return
            try:
                self._stream_validated_upstream(
                    vocaroo_media_url(vid),
                    lambda h: h in ('media.vocaroo.com', 'media1.vocaroo.com'),
                    'Vocaroo',
                    is_cover=False,
                )
            except urllib.error.HTTPError as exc:
                self._send_json(exc.code if 400 <= exc.code < 600 else 502, {'error': f'Vocaroo returned HTTP {exc.code}.'})
            except ValueError as exc:
                self._send_json(422, {'error': str(exc)})
            except Exception:
                self._send_json(502, {'error': 'Could not reach Vocaroo.'})
            return

        # 3. API: Check download job status
        if path.startswith('/api/omni/status/'):
            job_id = path.split('/api/omni/status/')[1].strip('/')
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job:
                self.send_error(404, "Job ID not found.")
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(job).encode('utf-8'))
            return

        # 4. API: Stream or download completed job file
        if path.startswith('/api/omni/download-file/'):
            job_id = path.split('/api/omni/download-file/')[1].strip('/')
            with JOBS_LOCK:
                job = JOBS.get(job_id)
            if not job or not job.get('filePath') or not os.path.isfile(job['filePath']):
                self.send_error(404, "File not ready or not found.")
                return

            fpath = job['filePath']
            fname = os.path.basename(fpath)
            fsize = os.path.getsize(fpath)
            ext = os.path.splitext(fname)[1].lower()

            mime = 'application/octet-stream'
            if ext == '.mp3': mime = 'audio/mpeg'
            elif ext == '.wav': mime = 'audio/wav'
            elif ext == '.m4a': mime = 'audio/mp4'
            elif ext == '.ogg': mime = 'audio/ogg'
            elif ext == '.opus': mime = 'audio/opus'
            elif ext == '.flac': mime = 'audio/flac'
            elif ext == '.aac': mime = 'audio/aac'
            elif ext == '.mp4': mime = 'video/mp4'
            elif ext == '.webm': mime = 'video/webm'

            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(fsize))
            self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
            self.end_headers()
            with open(fpath, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk: break
                    self.wfile.write(chunk)
            return

        # 5. API: Suno AI Metadata, Unshorten, Stream Proxy & Decrypt
        for suno_prefix in ('/api/suno/song/', '/api/suno/clip/', '/api/clip/', '/api/suno/playlist/', '/api/playlist/'):
            if path.startswith(suno_prefix):
                raw_id = path[len(suno_prefix):].strip('/')
                match = UUID_FULL_RE.match(raw_id)
                if not match:
                    self._send_json(400, {'error': 'A valid Suno UUID is required.'})
                    return
                clean_id = match.group(0).lower()
                kind = 'playlist' if 'playlist' in suno_prefix else 'clip'
                target = f"https://studio-api.prod.suno.com/api/{kind}/{clean_id}"
                if kind == 'playlist':
                    q = urllib.parse.parse_qs(parsed.query)
                    page = (q.get('page') or [''])[0].strip()
                    if page:
                        if not re.match(r'^[1-9][0-9]{0,3}$', page):
                            self._send_json(400, {'error': 'Invalid page number.'})
                            return
                        target += f"/?page={page}"
                try:
                    with _open_public_url(target, lambda h: h == 'studio-api.prod.suno.com', 'Suno AI', timeout=15) as resp:
                        raw_json = resp.read(4 * 1024 * 1024)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(raw_json)
                except urllib.error.HTTPError as exc:
                    self._send_json(exc.code if 400 <= exc.code < 600 else 502, {'error': f'Suno API returned HTTP {exc.code}.'})
                except ValueError as exc:
                    self._send_json(422, {'error': str(exc)})
                except Exception:
                    self._send_json(502, {'error': 'Could not reach Suno AI API.'})
                return

        if path == '/api/suno/unshorten':
            query = urllib.parse.parse_qs(parsed.query)
            raw_url = (query.get('url') or [''])[0].strip()
            if not raw_url:
                self._send_json(400, {'error': "Missing 'url' query parameter."})
                return
            m = UUID_REGEX.search(raw_url)
            if m and _host_matches(urllib.parse.urlparse(raw_url).hostname or '', 'suno.com'):
                sid = m.group(0).lower()
                self._send_json(200, {'status': 'ok', 'uuid': sid, 'target_url': f'https://suno.com/song/{sid}'})
                return
            try:
                with _open_public_url(raw_url, lambda h: _host_matches(h, 'suno.com') or _host_matches(h, 'suno.ai'), 'Suno AI', timeout=15) as resp:
                    final_url = resp.geturl() or ''
                m2 = UUID_REGEX.search(final_url)
                if not m2:
                    self._send_json(422, {'error': 'Could not resolve Suno shortlink to a valid track UUID.'})
                    return
                sid = m2.group(0).lower()
                self._send_json(200, {'status': 'ok', 'uuid': sid, 'target_url': f'https://suno.com/song/{sid}'})
            except ValueError as exc:
                self._send_json(422, {'error': str(exc)})
            except Exception:
                self._send_json(502, {'error': 'Could not resolve Suno shortlink.'})
            return

        if path.startswith('/api/suno/stream/'):
            raw_id = path[len('/api/suno/stream/'):].strip('/').split('.')[0]
            if not UUID_FULL_RE.match(raw_id):
                self._send_json(400, {'error': 'A valid Suno UUID is required.'})
                return
            clean_id = raw_id.lower()
            try:
                self._stream_validated_upstream(
                    f"https://d2lwuy8qc234o3.cloudfront.net/1/clip/{clean_id}.m4a",
                    lambda h: h == 'd2lwuy8qc234o3.cloudfront.net',
                    'Suno Audio',
                    is_cover=False,
                )
            except urllib.error.HTTPError as exc:
                self._send_json(exc.code if 400 <= exc.code < 600 else 502, {'error': f'Suno stream returned HTTP {exc.code}.'})
            except ValueError as exc:
                self._send_json(422, {'error': str(exc)})
            except Exception:
                self._send_json(502, {'error': 'Could not reach Suno stream CDN.'})
            return

        # 6. API: Decrypt Suno Song
        if path.startswith('/api/suno/decrypt/'):
            uuid = path.split('/api/suno/decrypt/')[1].strip('/').lower()
            try:
                decrypted = decrypt_suno_stream(uuid)
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mp4')
                self.send_header('Content-Length', str(len(decrypted)))
                self.send_header('Content-Disposition', f'attachment; filename="Suno_{uuid}.m4a"')
                self.end_headers()
                self.wfile.write(decrypted)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        super().handle_api_get()

    def handle_api_post(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 0. API: Stems Split-Vocals & Separate
        if path.startswith('/api/stems/split-vocals'):
            wav_bytes = self.read_body(MAX_STEM_BYTES)
            if wav_bytes is None:
                return
            if not wav_bytes:
                self._send_json(400, {'error': 'Empty vocal payload'})
                return
            try:
                sr, vocal_np = decode_wav_bytes_to_stereo_float32(wav_bytes)
                lead_np, back_np = split_lead_and_backing_vocals(vocal_np, sr)
                lead_wav = encode_stereo_float32_to_wav_bytes(lead_np, sr)
                back_wav = encode_stereo_float32_to_wav_bytes(back_np, sr)
                self._send_json(200, {
                    'status': 'done',
                    'lead_wav_base64': base64.b64encode(lead_wav).decode('ascii'),
                    'backing_wav_base64': base64.b64encode(back_wav).decode('ascii')
                })
            except Exception as exc:
                self._send_json(500, {'error': f"Failed to split vocals: {exc}"})
            return

        if path.startswith('/api/stems/separate'):
            caps = check_demucs_available()
            if not caps.get('available'):
                self._send_json(503, {'error': f"Local HTDemucs unavailable: {caps.get('error', 'missing packages')}"})
                return

            wav_bytes = self.read_body(MAX_STEM_BYTES)
            if wav_bytes is None:
                return
            if not wav_bytes:
                self._send_json(400, {'error': 'Empty audio payload'})
                return

            _prune_old_stem_jobs(max_jobs=3)

            job_id = uuid_lib.uuid4().hex[:12]
            _STEM_JOBS[job_id] = {
                'status': 'processing',
                'progress': 1,
                'stage': 'Queued for HTDemucs v4 neural separation...',
                'stems': None,
                'error': None,
                'created_at': time.time()
            }

            worker = threading.Thread(target=_run_demucs_job, args=(job_id, wav_bytes), daemon=True)
            worker.start()

            self._send_json(202, {'job_id': job_id, 'status': 'processing'})
            return

        if path == '/api/omni/cookies' and (
            self.trusted_origin or self.headers.get('Origin') != self.same_origin
            or self.headers.get_content_type() != 'application/json'
        ):
            self._send_json(403, {'error': 'Save cookies from the authenticated local helper page.'})
            return
        body = self.read_body(512 * 1024)
        if body is None:
            return

        # 1. API: Trigger download
        if path == '/api/omni/download':
            try:
                data = json.loads(body.decode('utf-8'))
                url = data.get('url')
                target_format = data.get('format', 'mp3')
                audio_only = bool(data.get('audioOnly', data.get('is_audio_only', False)))
                if not url:
                    self._send_json(400, {'error': "Missing 'url' field."})
                    return
                drm_plat = detect_drm_platform(url)
                if drm_plat:
                    self._send_json(422, {'error': drm_platform_error(drm_plat)})
                    return

                job_id = str(uuid_lib.uuid4())[:12]
                download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "downloads")
                t = threading.Thread(
                    target=download_media_task,
                    args=(job_id, url, target_format, audio_only, download_dir),
                    daemon=True
                )
                t.start()

                self._send_json(200, {'jobId': job_id, 'status': 'queued'})
            except Exception as e:
                self._send_json(500, {'error': str(e)})
            return

        # 2. API: Save Cookies
        if path == '/api/omni/cookies':
            try:
                data = json.loads(body)
                cookies = data.get('cookies') if isinstance(data, dict) else None
                contents = cookies.encode('utf-8') if isinstance(cookies, str) else None
                if contents is None or len(contents) > MAX_COOKIE_BYTES:
                    self._send_json(422, {'error': 'Provide a cookie file of at most 64 KiB.'})
                    return
                write_private_cookies(contents)
                self._send_json(200, {'success': True, 'message': 'Cookies saved to private local storage.'})
            except (ValueError, UnicodeError):
                self._send_json(400, {'error': 'Invalid cookie request.'})
            except OSError:
                self._send_json(500, {'error': 'Could not save the local cookie file.'})
            return

        # 3. Mango DRM Rights Proxy (for Suno)
        if path == '/api/mango/rights':
            try:
                rights_url = "https://studio-api.prod.suno.com/api/mango/rights"
                req = urllib.request.Request(
                    rights_url,
                    data=body,
                    headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp_data = resp.read()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(resp_data)
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        self.send_error(404, "Endpoint not found.")

    def _check_ffmpeg(self) -> bool:
        try:
            res = subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            return res.returncode == 0
        except Exception:
            return False


def run_server(port: int = 8899, directory=STUDIO_ROOT):
    copy_legacy_cookies()
    server = create_server(SoundLabHTTPHandler, port, directory)
    caps = check_demucs_available()
    print("=" * 70)
    print(f"[*] NTK SoundLab Studio Server Active on http://127.0.0.1:{port}")
    print(f"[*] Serving web app from: {os.path.abspath(directory)}")
    print(f"[*] Universal Media Extractor (yt-dlp): {'READY' if yt_dlp else 'NOT INSTALLED'}")
    print(f"[*] Neural Stems (HTDemucs v4): {'READY (' + caps['device'].upper() + ')' if caps['available'] else 'BROWSER WEBGPU/WASM ONNX'}")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="NTK SoundLab Studio Helper & Server")
    parser.add_argument("url", nargs="?", help="Universal media URL to download")
    parser.add_argument("--serve", action="store_true", default=True, help="Start local web server with yt-dlp & proxy")
    parser.add_argument("--port", type=int, default=8899, help="Port for server (default 8899)")
    parser.add_argument("--dir", default=STUDIO_ROOT, help="Studio asset directory")
    parser.add_argument("--format", default="mp3", help="Audio/video format (mp3, wav, flac, 1080p, 720p)")
    parser.add_argument("--audio-only", action="store_true", help="Fast grab audio stream only")
    args = parser.parse_args()

    if args.url:
        copy_legacy_cookies()
        print(f"[*] Extracting media from: {args.url}")
        job_id = "cli-" + str(uuid_lib.uuid4())[:8]
        download_media_task(job_id, args.url, target_format=args.format, audio_only=args.audio_only, output_dir="./downloads")
        res = JOBS.get(job_id)
        if res and res.get('filePath'):
            print(f"[+] Download complete: {res['filePath']}")
        else:
            print(f"[!] Error: {res.get('error') if res else 'Unknown'}")
        return

    if args.serve:
        run_server(port=args.port, directory=args.dir)


if __name__ == "__main__":
    main()
