<?php

namespace App\Services;

use App\Models\MediaDownload;
use GuzzleHttp\Psr7\Uri;
use GuzzleHttp\Psr7\UriResolver;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Str;
use InvalidArgumentException;
use RuntimeException;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\Process\Process;

class UniversalMediaService
{
    protected static ?string $cachedYtDlp = null;

    protected static ?string $cachedFfmpeg = null;

    protected string $downloadDir;

    protected string $cookiePath;

    public function __construct(protected SafeMediaHttp $http)
    {
        $this->downloadDir = storage_path('app/downloads');
        $this->cookiePath = storage_path('app/cookies.txt');
        File::ensureDirectoryExists($this->downloadDir, 0700);
    }

    public function cleanUrl(string $url): string
    {
        $url = $this->http->normalizeUrl($url);
        $host = strtolower(parse_url($url, PHP_URL_HOST));
        $path = parse_url($url, PHP_URL_PATH) ?: '/';
        if ($host === 'youtu.be' && preg_match('#^/([a-zA-Z0-9_-]{11})/?$#', $path, $match)) {
            return 'https://www.youtube.com/watch?v='.$match[1];
        }
        if ($host === 'm.youtube.com') {
            return preg_replace('#^https?://m\.youtube\.com#i', 'https://www.youtube.com', $url) ?: $url;
        }
        if ($host === 'instagr.am') {
            return preg_replace('#^https?://instagr\.am#i', 'https://www.instagram.com', $url) ?: $url;
        }
        if ($host === 'fxtwitter.com' || $host === 'vxtwitter.com') {
            return preg_replace('#^https?://(fx|vx)twitter\.com#i', 'https://x.com', $url) ?: $url;
        }
        if ($host === 'dai.ly' && preg_match('#^/([a-zA-Z0-9]+)#', $path, $match)) {
            return 'https://www.dailymotion.com/video/'.$match[1];
        }

        return $url;
    }

    public function isPublicHost(string $url): bool
    {
        try {
            $this->http->publicAddress($this->cleanUrl($url));

            return true;
        } catch (\Throwable) {
            return false;
        }
    }

    /** @return array<string, array{name: string, page_hosts: list<string>, cdn_hosts: list<string>, strip_suffixes: list<string>, canonical_fmt: string}> */
    protected function ogProviders(): array
    {
        return [
            'acemusic' => [
                'name' => 'ACE Music',
                'page_hosts' => ['acemusic.ai', 'www.acemusic.ai'],
                'cdn_hosts' => ['acemusic.ai', 'www.acemusic.ai', '.acemusic.ai', '.r2.cloudflarestorage.com', '.r2.dev'],
                'strip_suffixes' => [' | ACE Music', ' - ACE Music'],
                'canonical_fmt' => 'https://acemusic.ai/song/%s',
            ],
            'flowmusic' => [
                'name' => 'Flow Music',
                'page_hosts' => ['flowmusic.app', 'www.flowmusic.app', 'riffusion.com', 'www.riffusion.com', 'producer.ai', 'www.producer.ai'],
                'cdn_hosts' => ['flowmusic.app', 'www.flowmusic.app', '.flowmusic.app', '.riffusion.com', '.producer.ai', 'storage.googleapis.com'],
                'strip_suffixes' => [' | Flow Music', ' - Flow Music', ' | Riffusion', ' - Riffusion', ' | Producer.ai', ' - Producer.ai'],
                'canonical_fmt' => 'https://www.flowmusic.app/song/%s',
            ],
            'treblo' => [
                'name' => 'Treblo',
                'page_hosts' => ['treblo.com', 'www.treblo.com', 'sonauto.ai', 'www.sonauto.ai'],
                'cdn_hosts' => ['treblo.com', 'www.treblo.com', '.treblo.com', '.sonauto.ai', '.r2.cloudflarestorage.com'],
                'strip_suffixes' => [' | Treblo', ' - Treblo', ' | Sonauto', ' - Sonauto'],
                'canonical_fmt' => 'https://treblo.com/song/%s',
            ],
        ];
    }

    public function detectDrmPlatform(string $url): ?string
    {
        $host = strtolower(rtrim((string) (parse_url($url, PHP_URL_HOST) ?: ''), '.'));
        if ($host === '') {
            return null;
        }
        if (str_starts_with($host, 'music.amazon.')) {
            return 'Amazon Music';
        }
        foreach ([
            'audiomack.com' => 'Audiomack',
            'spotify.com' => 'Spotify',
            'music.apple.com' => 'Apple Music',
            'itunes.apple.com' => 'Apple Music',
            'tidal.com' => 'Tidal',
            'deezer.com' => 'Deezer',
            'pandora.com' => 'Pandora',
            'boomplay.com' => 'Boomplay',
        ] as $domain => $name) {
            if ($host === $domain || str_ends_with($host, '.'.$domain)) {
                return $name;
            }
        }

        return null;
    }

    public function drmPlatformMessage(string $platform): string
    {
        if ($platform === 'Audiomack') {
            return 'Audiomack requires signed OAuth playback credentials and its legacy public API no longer exposes audio streams. Play the track directly in Audiomack or import a local MP3/WAV/FLAC/M4A file into SoundLab Studio.';
        }

        return "{$platform} streams are DRM-protected and require an official {$platform} session/license. SoundLab Studio cannot extract DRM-encrypted tracks from {$platform}; please import a local MP3/WAV/FLAC/M4A file instead.";
    }

    public function detectPlatform(string $url): string
    {
        if ($drm = $this->detectDrmPlatform($url)) {
            return $drm;
        }
        $host = strtolower(parse_url($url, PHP_URL_HOST) ?: '');
        foreach ([
            'youtube.com' => 'YouTube',
            'youtu.be' => 'YouTube',
            'tiktok.com' => 'TikTok',
            'soundcloud.com' => 'SoundCloud',
            'snd.sc' => 'SoundCloud',
            'suno.com' => 'Suno AI',
            'suno.ai' => 'Suno AI',
            'acemusic.ai' => 'ACE Music',
            'flowmusic.app' => 'Flow Music',
            'riffusion.com' => 'Flow Music',
            'producer.ai' => 'Flow Music',
            'treblo.com' => 'Treblo',
            'sonauto.ai' => 'Treblo',
            'audius.co' => 'Audius',
            'vocaroo.com' => 'Vocaroo',
            'voca.ro' => 'Vocaroo',
            'bandcamp.com' => 'Bandcamp',
            'mixcloud.com' => 'Mixcloud',
            'freesound.org' => 'Freesound',
            'jamendo.com' => 'Jamendo',
            'archive.org' => 'Internet Archive',
            'dailymotion.com' => 'Dailymotion',
            'dai.ly' => 'Dailymotion',
            'twitch.tv' => 'Twitch',
            'bilibili.com' => 'Bilibili',
            'vimeo.com' => 'Vimeo',
            'instagram.com' => 'Instagram',
            'twitter.com' => 'Twitter/X',
            'x.com' => 'Twitter/X',
            'facebook.com' => 'Facebook',
            'fb.watch' => 'Facebook',
        ] as $domain => $name) {
            if ($host === $domain || str_ends_with($host, '.'.$domain)) {
                return $name;
            }
        }

        $path = parse_url($url, PHP_URL_PATH) ?: '';
        if (preg_match('/\.(m3u8|mpd)$/i', $path)) {
            return 'HLS/DASH Stream';
        }

        return preg_match('/\.(mp3|wav|m4a|aac|flac|ogg|opus|mp4|webm|mov|mkv)$/i', $path) ? 'Direct Media File' : 'Universal';
    }

    public function extractOgProviderId(string $provider, string $raw): ?string
    {
        $cfg = $this->ogProviders()[$provider] ?? null;
        if (! $cfg) {
            return null;
        }
        $raw = trim($raw);
        if (preg_match('/^[a-zA-Z0-9_-]{4,64}$/', $raw)) {
            return $raw;
        }
        $host = strtolower(rtrim((string) (parse_url($raw, PHP_URL_HOST) ?: ''), '.'));
        if (! in_array($host, $cfg['page_hosts'], true)) {
            return null;
        }
        $parts = array_values(array_filter(explode('/', trim((string) (parse_url($raw, PHP_URL_PATH) ?: ''), '/')), fn ($p) => $p !== ''));
        if (count($parts) === 2 && in_array($parts[0], ['song', 'songs'], true) && preg_match('/^[a-zA-Z0-9_-]{4,64}$/', $parts[1])) {
            return $parts[1];
        }
        if (count($parts) === 3 && preg_match('/^[a-zA-Z]{2,5}(?:-[a-zA-Z0-9]{2,8})?$/', $parts[0]) && in_array($parts[1], ['song', 'songs'], true) && preg_match('/^[a-zA-Z0-9_-]{4,64}$/', $parts[2])) {
            return $parts[2];
        }

        return null;
    }

    public function detectOgProviderForUrl(string $url): ?string
    {
        foreach (array_keys($this->ogProviders()) as $key) {
            if ($this->extractOgProviderId($key, $url) !== null) {
                return $key;
            }
        }

        return null;
    }

    public function extractAceMusicId(string $raw): ?string
    {
        return $this->extractOgProviderId('acemusic', $raw);
    }

    protected function extractHtmlMeta(string $html, string $targetKey): string
    {
        $want = strtolower($targetKey);
        if (! preg_match_all('/<meta\b[^>]*>/i', $html, $tags)) {
            return '';
        }
        foreach ($tags[0] as $tag) {
            $key = '';
            $content = '';
            if (preg_match_all('/([a-zA-Z_:][-a-zA-Z0-9_.:]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')/', $tag, $attrs, PREG_SET_ORDER)) {
                foreach ($attrs as $attr) {
                    $name = strtolower($attr[1]);
                    $val = $attr[2] !== '' ? $attr[2] : ($attr[3] ?? '');
                    if ($name === 'property' || $name === 'name') {
                        $key = strtolower(trim($val));
                    } elseif ($name === 'content') {
                        $content = html_entity_decode(trim($val), ENT_QUOTES | ENT_HTML5, 'UTF-8');
                    }
                }
            }
            if ($key === $want && $content !== '') {
                return $content;
            }
        }

        return '';
    }

    /** @return array{meta: array<string, mixed>, audio_url: string, cover_url: string} */
    public function resolveOgProvider(string $provider, string $rawUrlOrId): array
    {
        $cfg = $this->ogProviders()[$provider] ?? null;
        if (! $cfg) {
            throw new InvalidArgumentException('Unsupported provider.');
        }
        $label = $cfg['name'];
        $id = $this->extractOgProviderId($provider, $rawUrlOrId);
        if (! $id) {
            throw new InvalidArgumentException("A valid {$label} song link or ID is required.");
        }
        $pageUrl = sprintf($cfg['canonical_fmt'], $id);
        $response = $this->http->request($pageUrl, maxBytes: 2097152, allowedHosts: $cfg['page_hosts']);
        if ($response['status'] < 200 || $response['status'] >= 300) {
            throw new HttpException($response['status'] >= 400 && $response['status'] < 600 ? $response['status'] : 502, "{$label} song page is unavailable.");
        }
        $ctype = strtolower(trim(explode(';', $response['headers']['content-type'] ?? '')[0]));
        if ($ctype !== '' && $ctype !== 'text/html' && $ctype !== 'application/xhtml+xml') {
            throw new HttpException(502, "{$label} returned an unexpected response type.");
        }
        $html = $response['body'];
        $baseUrl = $response['url'] ?: $pageUrl;
        $audioRaw = $this->extractHtmlMeta($html, 'og:audio');
        if ($audioRaw === '' && preg_match('/<audio\b[^>]*\bsrc\s*=\s*(?:"([^"]*)"|\'([^\']*)\')/i', $html, $audioMatch)) {
            $audioRaw = html_entity_decode(trim($audioMatch[1] ?: ($audioMatch[2] ?? '')), ENT_QUOTES | ENT_HTML5, 'UTF-8');
        }
        if ($audioRaw === '') {
            throw new HttpException(422, "{$label} did not expose a public audio stream for this link.");
        }
        $audioUrl = $this->http->normalizeUrl((string) UriResolver::resolve(new Uri($baseUrl), new Uri($audioRaw)));
        $audioHost = strtolower(rtrim((string) (parse_url($audioUrl, PHP_URL_HOST) ?: ''), '.'));
        if (parse_url($audioUrl, PHP_URL_SCHEME) !== 'https' || ! $this->http->hostMatchesAllowlist($audioHost, $cfg['cdn_hosts'])) {
            throw new HttpException(502, "{$label} returned an unsupported audio destination.");
        }

        $coverUrl = '';
        $coverRaw = $this->extractHtmlMeta($html, 'og:image');
        if ($coverRaw !== '') {
            try {
                $candidate = $this->http->normalizeUrl((string) UriResolver::resolve(new Uri($baseUrl), new Uri($coverRaw)));
                $coverHost = strtolower(rtrim((string) (parse_url($candidate, PHP_URL_HOST) ?: ''), '.'));
                if (parse_url($candidate, PHP_URL_SCHEME) === 'https' && $this->http->hostMatchesAllowlist($coverHost, $cfg['cdn_hosts'])) {
                    $coverUrl = $candidate;
                }
            } catch (\Throwable) {
                $coverUrl = '';
            }
        }

        $rawTitle = trim($this->extractHtmlMeta($html, 'og:title'));
        foreach ($cfg['strip_suffixes'] as $suffix) {
            if (str_ends_with($rawTitle, $suffix)) {
                $rawTitle = trim(substr($rawTitle, 0, -strlen($suffix)));
            }
        }
        $title = $rawTitle;
        $artist = $label;
        foreach ([' by ', ' par '] as $sep) {
            $pos = strrpos($rawTitle, $sep);
            if ($pos !== false && $pos > 0) {
                $t = trim(substr($rawTitle, 0, $pos));
                $a = trim(substr($rawTitle, $pos + strlen($sep)));
                if ($t !== '' && $a !== '') {
                    $title = $t;
                    $artist = $a;
                    break;
                }
            }
        }
        if ($title === '') {
            $shortId = strlen($id) > 16 ? substr($id, 0, 8) : $id;
            $title = $label.'_'.$shortId;
        }
        $desc = $this->extractHtmlMeta($html, 'description') ?: $this->extractHtmlMeta($html, 'og:description');
        $coverProxy = $coverUrl !== '' ? "/api/{$provider}/cover/{$id}" : '';
        $streamProxy = "/api/{$provider}/stream/{$id}";
        $normId = strtolower($id);

        return [
            'meta' => [
                'type' => 'single',
                'uuid' => "{$provider}-{$normId}",
                'id' => $normId,
                'title' => $title,
                'artist' => $artist,
                'artist_name' => $artist,
                'imageLarge' => $coverProxy,
                'imageThumb' => $coverProxy,
                'image_url' => $coverProxy,
                'streamUrl' => $streamProxy,
                'direct_stream_url' => $streamProxy,
                'duration' => 0,
                'prompt' => $desc,
                'url' => $baseUrl,
                'platform' => $label,
                'format' => strtoupper(pathinfo((string) parse_url($audioUrl, PHP_URL_PATH), PATHINFO_EXTENSION) ?: 'MP3'),
                'hasVideo' => false,
                'hasAudio' => true,
                'hasStem' => true,
                'tags' => "{$label} • {$artist}",
            ],
            'audio_url' => $audioUrl,
            'cover_url' => $coverUrl,
        ];
    }

    /** @return array{meta: array<string, mixed>, audio_url: string, cover_url: string} */
    public function resolveAceMusic(string $rawUrlOrId): array
    {
        return $this->resolveOgProvider('acemusic', $rawUrlOrId);
    }

    /** @return array{status: int, headers: array<string, string>, content_type: string} */
    protected function streamUrlToDestination(string $target, string $kind, ?string $range, string $destination, array $allowedHosts = []): array
    {
        $maxBytes = $kind === 'cover' ? 16 * 1024 * 1024 : 150 * 1024 * 1024;
        $headers = $range ? ['Range' => $range] : [];
        $result = $this->http->request($target, headers: $headers, maxBytes: $maxBytes, destination: $destination, allowedHosts: $allowedHosts);
        if (! in_array($result['status'], [200, 206], true)) {
            throw new HttpException($result['status'] >= 400 && $result['status'] < 600 ? $result['status'] : 502, 'The audio provider could not supply this track.');
        }
        $ctype = strtolower(trim(explode(';', $result['headers']['content-type'] ?? '')[0]));
        $explicitMedia = ['audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/m4a', 'audio/x-m4a', 'audio/aac', 'audio/x-aac', 'audio/aacp', 'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/ogg', 'audio/opus', 'audio/flac', 'audio/x-flac', 'audio/webm', 'video/mp4', 'video/webm', 'video/quicktime', 'application/ogg'];
        $allowedMimes = match ($kind) {
            'cover' => ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'],
            'strict_media' => $explicitMedia,
            default => [...$explicitMedia, 'application/octet-stream', 'binary/octet-stream'],
        };
        if (! in_array($ctype, $allowedMimes, true)) {
            throw new HttpException(502, 'The audio provider returned an unexpected content type.');
        }

        return ['status' => $result['status'], 'headers' => $result['headers'], 'content_type' => $ctype];
    }

    /** @return array{status: int, headers: array<string, string>, content_type: string} */
    public function fetchOgProviderMedia(string $provider, string $id, string $kind, ?string $range, string $destination): array
    {
        $cfg = $this->ogProviders()[$provider] ?? null;
        if (! $cfg) {
            throw new InvalidArgumentException('Unsupported provider.');
        }
        $resolved = $this->resolveOgProvider($provider, $id);
        $target = $kind === 'cover' ? $resolved['cover_url'] : $resolved['audio_url'];
        if ($target === '') {
            throw new HttpException(404, "No cover artwork is available for this {$cfg['name']} track.");
        }
        $host = strtolower((string) parse_url($target, PHP_URL_HOST));
        $allowed = array_values(array_unique([...$cfg['cdn_hosts'], $host]));

        return $this->streamUrlToDestination($target, $kind, $range, $destination, $allowed);
    }

    /** @return array{status: int, headers: array<string, string>, content_type: string} */
    public function fetchAceMusicMedia(string $id, string $kind, ?string $range, string $destination): array
    {
        return $this->fetchOgProviderMedia('acemusic', $id, $kind, $range, $destination);
    }

    /** @return array<string, mixed> */
    protected function formatAudiusTrack(array $track, string $webpageUrl = ''): array
    {
        $tid = (string) ($track['id'] ?? '');
        $artist = trim((string) ($track['user']['name'] ?? $track['user']['handle'] ?? '')) ?: 'Audius Creator';
        $artwork = is_array($track['artwork'] ?? null) ? $track['artwork'] : [];
        $hasArt = ! empty($artwork['1000x1000']) || ! empty($artwork['480x480']) || ! empty($artwork['150x150']);
        $coverProxy = $hasArt ? '/api/audius/cover/'.$tid : '';
        $genre = trim((string) ($track['genre'] ?? '')) ?: 'Audius';

        return [
            'uuid' => 'audius-'.strtolower($tid),
            'id' => $tid,
            'title' => trim((string) ($track['title'] ?? '')) ?: 'Audius_'.$tid,
            'artist' => $artist,
            'artist_name' => $artist,
            'imageLarge' => $coverProxy,
            'imageThumb' => $coverProxy,
            'image_url' => $coverProxy,
            'streamUrl' => '/api/audius/stream/'.$tid,
            'direct_stream_url' => '/api/audius/stream/'.$tid,
            'duration' => max(0, (int) ($track['duration'] ?? 0)),
            'prompt' => (string) ($track['description'] ?? ''),
            'url' => $webpageUrl ?: 'https://audius.co'.((string) ($track['permalink'] ?? '')),
            'platform' => 'Audius',
            'format' => 'MP3',
            'hasVideo' => false,
            'hasAudio' => true,
            'hasStem' => true,
            'tags' => "Audius • {$genre} • {$artist}",
        ];
    }

    /** @return array<string, mixed> */
    public function resolveAudius(string $rawUrl): array
    {
        $res = $this->http->request(
            'https://api.audius.co/v1/resolve?url='.rawurlencode(trim($rawUrl)),
            headers: ['Accept' => 'application/json'],
            maxBytes: 2097152,
            allowedHosts: ['api.audius.co']
        );
        if ($res['status'] < 200 || $res['status'] >= 300) {
            throw new HttpException(422, 'Audius API returned HTTP '.$res['status'].'.');
        }
        $payload = json_decode($res['body'], true);
        $data = is_array($payload) ? ($payload['data'] ?? null) : null;
        if (is_array($data) && isset($data['tracks']) && is_array($data['tracks'])) {
            $clips = array_values(array_filter(array_map(
                fn ($t) => is_array($t) && preg_match('/^[a-zA-Z0-9_-]{3,32}$/', (string) ($t['id'] ?? '')) ? $this->formatAudiusTrack($t) : null,
                $data['tracks']
            )));
            if (! $clips) {
                throw new HttpException(422, 'Audius playlist has no streamable tracks.');
            }

            return [
                'type' => 'playlist',
                'id' => (string) ($data['id'] ?? $clips[0]['id']),
                'title' => (string) ($data['playlist_name'] ?? 'Audius Playlist'),
                'uploader' => (string) ($data['user']['name'] ?? 'Audius'),
                'count' => count($clips),
                'clips' => $clips,
            ];
        }
        if (is_array($data) && preg_match('/^[a-zA-Z0-9_-]{3,32}$/', (string) ($data['id'] ?? ''))) {
            $track = $this->formatAudiusTrack($data, trim($rawUrl));
            $track['type'] = 'single';

            return $track;
        }
        throw new HttpException(422, 'Audius did not return a playable track for this link.');
    }

    /** @return array{status: int, headers: array<string, string>, content_type: string} */
    public function fetchAudiusMedia(string $id, string $kind, ?string $range, string $destination): array
    {
        if (! preg_match('/^[a-zA-Z0-9_-]{3,32}$/', $id)) {
            throw new InvalidArgumentException('A valid Audius track ID is required.');
        }
        if ($kind === 'cover') {
            $meta = $this->http->request('https://api.audius.co/v1/tracks/'.$id, headers: ['Accept' => 'application/json'], maxBytes: 1048576, allowedHosts: ['api.audius.co']);
            $data = json_decode($meta['body'], true)['data'] ?? [];
            $art = is_array($data['artwork'] ?? null) ? $data['artwork'] : [];
            $target = $art['1000x1000'] ?? $art['480x480'] ?? $art['150x150'] ?? '';
            if (! $target || parse_url($target, PHP_URL_SCHEME) !== 'https') {
                throw new HttpException(404, 'No cover artwork is available for this Audius track.');
            }
            $candidates = [$target];
            $artPath = (string) (parse_url($target, PHP_URL_PATH) ?: '');
            $artQuery = (string) (parse_url($target, PHP_URL_QUERY) ?: '');
            $suffix = $artPath.($artQuery !== '' ? '?'.$artQuery : '');
            foreach ((array) ($art['mirrors'] ?? []) as $mirror) {
                $mParts = parse_url(trim((string) $mirror));
                if (($mParts['scheme'] ?? '') === 'https' && ! empty($mParts['host'])) {
                    $alt = 'https://'.$mParts['host'].$suffix;
                    if (! in_array($alt, $candidates, true)) {
                        $candidates[] = $alt;
                    }
                    if (count($candidates) >= 4) {
                        break;
                    }
                }
            }
            $lastError = null;
            foreach ($candidates as $cand) {
                try {
                    return $this->streamUrlToDestination($cand, 'cover', $range, $destination);
                } catch (\Throwable $e) {
                    $lastError = $e;
                }
            }
            throw $lastError;
        }

        return $this->streamUrlToDestination("https://api.audius.co/v1/tracks/{$id}/stream", 'audio', $range, $destination);
    }

    public function vocarooMp3Url(string $id): string
    {
        $sub = (strlen($id) === 10 || (strlen($id) === 12 && str_starts_with($id, '1'))) ? 'media1' : 'media';

        return "https://{$sub}.vocaroo.com/mp3/{$id}";
    }

    /** @return array<string, mixed> */
    public function resolveVocaroo(string $rawUrl): array
    {
        $parts = array_values(array_filter(explode('/', trim((string) (parse_url($rawUrl, PHP_URL_PATH) ?: ''), '/')), fn ($p) => $p !== ''));
        $id = '';
        if (count($parts) === 1 && preg_match('/^[a-zA-Z0-9_-]{6,24}$/', $parts[0])) {
            $id = $parts[0];
        } elseif (count($parts) === 2 && in_array($parts[0], ['embed', 'i'], true) && preg_match('/^[a-zA-Z0-9_-]{6,24}$/', $parts[1])) {
            $id = $parts[1];
        }
        if ($id === '') {
            throw new InvalidArgumentException('A valid Vocaroo recording link is required.');
        }
        $probe = $this->http->request(
            $this->vocarooMp3Url($id),
            method: 'HEAD',
            maxBytes: 65536,
            allowedHosts: ['media.vocaroo.com', 'media1.vocaroo.com']
        );
        if (in_array($probe['status'], [404, 410], true)) {
            throw new HttpException(422, 'Vocaroo recording was not found or has expired.');
        }
        if ($probe['status'] < 200 || $probe['status'] >= 400) {
            throw new HttpException(422, 'Vocaroo media CDN returned HTTP '.$probe['status'].'.');
        }

        return [
            'type' => 'single',
            'uuid' => 'vocaroo-'.strtolower($id),
            'id' => $id,
            'title' => 'Vocaroo_'.$id,
            'artist' => 'Vocaroo Voice Recording',
            'artist_name' => 'Vocaroo Voice Recording',
            'imageLarge' => '',
            'imageThumb' => '',
            'image_url' => '',
            'streamUrl' => '/api/vocaroo/stream/'.$id,
            'direct_stream_url' => '/api/vocaroo/stream/'.$id,
            'duration' => 0,
            'prompt' => '',
            'url' => 'https://vocaroo.com/'.$id,
            'platform' => 'Vocaroo',
            'format' => 'MP3',
            'hasVideo' => false,
            'hasAudio' => true,
            'hasStem' => true,
            'tags' => 'Vocaroo • Voice Note',
        ];
    }

    /** @return array{status: int, headers: array<string, string>, content_type: string} */
    public function fetchVocarooMedia(string $id, ?string $range, string $destination): array
    {
        if (! preg_match('/^[a-zA-Z0-9_-]{6,24}$/', $id)) {
            throw new InvalidArgumentException('A valid Vocaroo ID is required.');
        }

        return $this->streamUrlToDestination($this->vocarooMp3Url($id), 'audio', $range, $destination, ['media.vocaroo.com', 'media1.vocaroo.com']);
    }

    /** @return array{status: int, headers: array<string, string>, content_type: string} */
    public function fetchDirectMedia(string $rawUrl, ?string $range, string $destination, bool $allowExtensionlessStrict = false): array
    {
        $url = $this->cleanUrl($rawUrl);
        $path = parse_url($url, PHP_URL_PATH) ?: '';
        $ext = pathinfo($path, PATHINFO_EXTENSION);
        if (! preg_match('/\.(mp3|wav|m4a|aac|flac|ogg|opus|mp4|webm|mov|mkv)$/i', $path)) {
            if (! $allowExtensionlessStrict || $ext !== '') {
                throw new HttpException(422, 'Only direct audio/video media files can be streamed through this endpoint.');
            }

            return $this->streamUrlToDestination($url, 'strict_media', $range, $destination);
        }

        return $this->streamUrlToDestination($url, 'audio', $range, $destination);
    }

    public function getStorageUsedBytes(): int
    {
        return array_sum(array_map(fn ($file): int => $file->getSize(), File::allFiles($this->downloadDir)));
    }

    public function getCapabilities(): array
    {
        $used = $this->getStorageUsedBytes();
        $budget = (int) config('media.download_budget_bytes', 524288000);

        return [
            'status' => 'ok', 'server' => 'NTK SoundLab Studio (Laravel Edition)', 'php_version' => PHP_VERSION,
            'yt_dlp' => (bool) config('media.extractor_egress_sandboxed') && (bool) $this->findBinary(['yt-dlp', 'yt-dlp.exe']),
            'ffmpeg' => (bool) $this->findBinary(['ffmpeg', 'ffmpeg.exe']),
            'mobile_api_bypass' => false, 'zero_disk_streaming' => false,
            'cookie_configured' => is_file($this->cookiePath) && filesize($this->cookiePath) > 0,
            'storage' => ['downloads_bytes' => $used, 'downloads_formatted' => $this->formatBytes($used),
                'quota_limit_bytes' => $budget, 'quota_limit_formatted' => $this->formatBytes($budget),
                'quota_used_pct' => round(100 * $used / max(1, $budget), 2), 'safe_threshold_ok' => $used < $budget,
                'scope' => 'Application download budget; excludes other hosting usage'],
            'timestamp' => now()->toIso8601String(),
        ];
    }

    public function resolveMetadata(string $rawUrl): array
    {
        $url = $this->cleanUrl($rawUrl);
        if ($drm = $this->detectDrmPlatform($url)) {
            throw new HttpException(422, $this->drmPlatformMessage($drm));
        }
        $platform = $this->detectPlatform($url);
        $this->http->publicAddress($url);
        if ($ogProvider = $this->detectOgProviderForUrl($url)) {
            return $this->resolveOgProvider($ogProvider, $url)['meta'];
        }
        if ($platform === 'Audius') {
            return $this->resolveAudius($url);
        }
        if ($platform === 'Vocaroo') {
            return $this->resolveVocaroo($url);
        }
        $meta = [];
        $hasYtDlp = config('media.extractor_egress_sandboxed') && ($binary = $this->findBinary(['yt-dlp', 'yt-dlp.exe']));
        if ($hasYtDlp) {
            $process = new Process([$binary, '--ignore-config', '--no-cache-dir', '--no-playlist', '--dump-single-json', '--skip-download', '--', $url]);
            $process->setTimeout(20);
            $process->run();
            if ($process->isSuccessful() && strlen($process->getOutput()) <= 2097152) {
                $meta = json_decode($process->getOutput(), true) ?: [];
            }
        }
        $oembed = match ($platform) {
            'YouTube' => 'https://www.youtube.com/oembed',
            'SoundCloud' => 'https://soundcloud.com/oembed',
            'TikTok' => 'https://www.tiktok.com/oembed',
            'Vimeo' => 'https://vimeo.com/api/oembed.json',
            default => null,
        };
        if (! $meta && $oembed) {
            $response = $this->http->request($oembed.'?'.http_build_query(['url' => $url, 'format' => 'json']));
            if ($response['status'] === 200) {
                $meta = json_decode($response['body'], true) ?: [];
            }
        }
        if (! $meta && $platform === 'HLS/DASH Stream') {
            throw new HttpException(422, 'HLS/DASH playlist manifests (.m3u8/.mpd) require yt-dlp and FFmpeg on the host or local Python helper.');
        }
        if (! $meta && $platform !== 'Direct Media File') {
            throw new HttpException(503, 'This host cannot safely resolve this link. Use a direct public media file or the local desktop helper.');
        }
        $title = $meta['title'] ?? pathinfo(parse_url($url, PHP_URL_PATH), PATHINFO_FILENAME);
        $artist = $meta['uploader'] ?? $meta['author_name'] ?? $platform;
        $image = $meta['thumbnail'] ?? $meta['thumbnail_url'] ?? asset('assets/icon.svg');
        $isDirect = $platform === 'Direct Media File';
        $directProxy = $isDirect ? '/api/omni/direct-stream?url='.rawurlencode($url) : null;

        return [
            'uuid' => ($isDirect ? 'direct-' : 'omni-').substr(hash('sha256', $url), 0, 12),
            'title' => $title ?: 'Media',
            'artist' => $artist,
            'artist_name' => $artist,
            'imageLarge' => $image,
            'image_url' => $image,
            'duration' => max(0, (int) ($meta['duration'] ?? 0)),
            'prompt' => '',
            'url' => $url,
            'platform' => $platform,
            'format' => strtoupper($meta['ext'] ?? pathinfo(parse_url($url, PHP_URL_PATH), PATHINFO_EXTENSION)),
            'streamUrl' => $directProxy,
            'direct_stream_url' => $directProxy,
            'hasAudio' => true,
            'hasStem' => true,
        ];
    }

    public function streamPassthrough(string $rawUrl, string $format = 'mp3', bool $isAudioOnly = true): never
    {
        $this->cleanUrl($rawUrl);
        throw new HttpException(503, 'Unbuffered media conversion is unavailable. Use the bounded download endpoint or local desktop helper.');
    }

    public function startDownload(string $rawUrl, string $format = 'mp3', bool $isAudioOnly = true): MediaDownload
    {
        $url = $this->cleanUrl($rawUrl);
        if ($drm = $this->detectDrmPlatform($url)) {
            throw new HttpException(422, $this->drmPlatformMessage($drm));
        }
        $format = strtolower($format);
        if (! in_array($format, ['mp3', 'wav', 'm4a', 'flac', 'ogg', 'mp4', 'webm'], true)) {
            throw new InvalidArgumentException('Unsupported output format.');
        }
        $this->http->publicAddress($url);
        $lock = $this->acquireLock();
        if (! $lock) {
            throw new HttpException(429, 'Another download is processing. Please retry shortly.');
        }
        try {
            $maxBytes = (int) config('media.max_download_bytes', 157286400);
            if ($this->getStorageUsedBytes() + 2 * $maxBytes > (int) config('media.download_budget_bytes', 524288000)) {
                throw new HttpException(507, 'The application download budget has insufficient space.');
            }
            $download = MediaDownload::create(['id' => 'dl_'.Str::random(16), 'url' => $url,
                'platform' => $this->detectPlatform($url), 'format' => $format, 'status' => 'processing', 'progress' => 5]);
            $this->executeDownload($download, $isAudioOnly);

            return $download->fresh();
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }

    public function executeDownload(MediaDownload $download, bool $isAudioOnly): void
    {
        $base = $this->downloadDir.DIRECTORY_SEPARATOR.$download->id;
        $source = $base.'.source';
        $output = $base.'.'.$download->format;
        $maxBytes = (int) config('media.max_download_bytes', 157286400);
        try {
            $ffmpeg = $this->findBinary(['ffmpeg', 'ffmpeg.exe']);
            if (! $ffmpeg) {
                throw new RuntimeException('Media conversion requires FFmpeg on this server. Use the local desktop helper.');
            }
            if ($download->platform === 'Direct Media File') {
                $response = $this->http->request($download->url, maxBytes: $maxBytes, destination: $source);
                if ($response['status'] !== 200 || ! is_file($source) || filesize($source) === 0) {
                    throw new RuntimeException('The media server did not return a complete media file.');
                }
            } else {
                if (! config('media.extractor_egress_sandboxed') || ! ($extractor = $this->findBinary(['yt-dlp', 'yt-dlp.exe']))) {
                    throw new RuntimeException('Hosted extraction is unavailable without a public-network egress sandbox. Use the local desktop helper or a direct media file.');
                }
                $args = [$extractor, '--ignore-config', '--no-cache-dir', '--no-playlist', '--no-part', '--max-filesize', (string) $maxBytes,
                    '-f', $isAudioOnly ? 'bestaudio/best' : 'best[height<=1080]/best', '-o', $source, '--', $download->url];
                $this->runBoundedProcess(new Process($args), [$source], $maxBytes);
            }
            $audio = in_array($download->format, ['mp3', 'wav', 'm4a', 'flac', 'ogg'], true);
            if ($isAudioOnly && ! $audio) {
                throw new RuntimeException('Choose an audio output format for an audio-only download.');
            }
            $args = [$ffmpeg, '-nostdin', '-y', '-protocol_whitelist', 'file,pipe', '-format_whitelist', 'aac,flac,matroska,webm,mov,mp3,ogg,wav', '-i', $source];
            if ($audio) {
                array_push($args, '-vn');
            }
            array_push($args, '-fs', (string) ($maxBytes + 1), $output);
            $this->runBoundedProcess(new Process($args), [$source, $output], $maxBytes);
            clearstatcache(true, $output);
            if (! is_file($output) || is_link($output) || filesize($output) < 1 || filesize($output) > $maxBytes) {
                throw new RuntimeException('Media conversion did not produce a valid bounded output.');
            }
            $mime = File::mimeType($output) ?: '';
            if (! str_starts_with($mime, 'audio/') && ! str_starts_with($mime, 'video/') && ! in_array($mime, ['application/ogg', 'application/octet-stream'], true)) {
                throw new RuntimeException('The converted output is not recognized as media.');
            }
            $download->update(['status' => 'completed', 'progress' => 100, 'file_path' => $output,
                'file_size' => filesize($output), 'expires_at' => now()->addMinutes(30)]);
        } catch (\Throwable $error) {
            $this->removeJobFiles($download->id);
            $download->update(['status' => 'failed', 'progress' => 0, 'file_path' => null, 'file_size' => 0,
                'error' => $error instanceof RuntimeException ? $error->getMessage() : 'Media processing failed.', 'expires_at' => now()->addMinutes(30)]);
        } finally {
            if (is_file($source) && ! is_link($source)) {
                unlink($source);
            }
        }
    }

    protected function runBoundedProcess(Process $process, array $paths, int $maxBytes): void
    {
        $process->setTimeout(180);
        $process->disableOutput();
        $process->start();
        try {
            while ($process->isRunning()) {
                $process->checkTimeout();
                foreach ($paths as $path) {
                    clearstatcache(true, $path);
                    if (is_file($path) && filesize($path) > $maxBytes) {
                        $process->stop(0.2);
                        throw new RuntimeException('Media exceeds the allowed output size.');
                    }
                }
                if (connection_aborted()) {
                    $process->stop(0.2);
                    throw new RuntimeException('Download was cancelled.');
                }
                usleep(50000);
            }
            if (! $process->isSuccessful()) {
                throw new RuntimeException('Media extraction or conversion failed; incomplete output was discarded.');
            }
        } finally {
            if ($process->isRunning()) {
                $process->stop(0.2);
            }
        }
    }

    public function saveCookies(string $cookieContent): bool
    {
        if (strlen($cookieContent) > 65536 || ($cookieContent !== '' && ! str_contains($cookieContent, '# Netscape HTTP Cookie File'))) {
            throw new InvalidArgumentException('A Netscape cookie file of at most 64 KB is required.');
        }
        $temporary = $this->cookiePath.'.tmp';
        if (file_put_contents($temporary, trim($cookieContent), LOCK_EX) === false) {
            return false;
        }
        @chmod($temporary, 0600);

        return rename($temporary, $this->cookiePath);
    }

    public function getCookies(): string
    {
        return is_file($this->cookiePath) ? (string) file_get_contents($this->cookiePath) : '';
    }

    /** @return resource|false */
    protected function acquireLock()
    {
        $handle = fopen(storage_path('app/downloads.lock'), 'c');
        if (! $handle || ! flock($handle, LOCK_EX | LOCK_NB)) {
            if ($handle) {
                fclose($handle);
            }

            return false;
        }

        return $handle;
    }

    public function containedDownloadPath(string $path): bool
    {
        $real = realpath($path);
        $root = realpath($this->downloadDir);
        if ($real === false || $root === false || is_link($path) || ! is_file($real)) {
            return false;
        }
        if (DIRECTORY_SEPARATOR === '\\') {
            $real = strtolower($real);
            $root = strtolower($root);
        }

        return str_starts_with($real, $root.DIRECTORY_SEPARATOR);
    }

    protected function removeJobFiles(string $id): void
    {
        if (! preg_match('/^dl_[A-Za-z0-9]{16}$/', $id)) {
            return;
        }
        foreach (glob($this->downloadDir.DIRECTORY_SEPARATOR.$id.'.*') ?: [] as $path) {
            if ($this->containedDownloadPath($path)) {
                unlink($path);
            }
        }
    }

    public function pruneExpiredDownloads(int $maxAgeMinutes = 30): int
    {
        if ($maxAgeMinutes < 1 || $maxAgeMinutes > 10080) {
            throw new InvalidArgumentException('max-age must be between 1 and 10080 minutes.');
        }
        $lock = $this->acquireLock();
        if (! $lock) {
            return 0;
        }
        $count = 0;
        try {
            // The shared execution lock proves no synchronous worker is active.
            foreach (MediaDownload::whereIn('status', ['processing', 'queued'])->where('updated_at', '<=', now()->subMinutes(max(30, $maxAgeMinutes)))->get() as $stale) {
                $this->removeJobFiles($stale->id);
                $stale->update(['status' => 'failed', 'error' => 'An interrupted download expired; incomplete files were discarded.', 'file_path' => null, 'file_size' => 0, 'progress' => 0, 'expires_at' => now()->addMinutes(30)]);
            }
            $jobs = MediaDownload::whereIn('status', ['completed', 'failed'])
                ->where('expires_at', '<=', now())->where('updated_at', '<=', now()->subMinutes($maxAgeMinutes))->get();
            foreach ($jobs as $job) {
                $handle = null;
                if ($job->file_path && file_exists($job->file_path)) {
                    if (! $this->containedDownloadPath($job->file_path)) {
                        continue;
                    }
                    $handle = fopen($job->file_path, 'rb');
                    if (! $handle || ! flock($handle, LOCK_EX | LOCK_NB)) {
                        if ($handle) {
                            fclose($handle);
                        }

                        continue;
                    }
                    flock($handle, LOCK_UN);
                    fclose($handle);
                    // Readers hold the shared global lock through response completion.
                    if (! unlink($job->file_path)) {
                        continue;
                    }
                }
                $this->removeJobFiles($job->id);
                $job->delete();
                $count++;
            }

            return $count;
        } finally {
            flock($lock, LOCK_UN);
            fclose($lock);
        }
    }

    protected function findBinary(array $binaryNames): ?string
    {
        $isFfmpeg = in_array('ffmpeg', $binaryNames) || in_array('ffmpeg.exe', $binaryNames);
        if ($isFfmpeg && self::$cachedFfmpeg !== null) {
            return self::$cachedFfmpeg;
        }
        if (! $isFfmpeg && self::$cachedYtDlp !== null) {
            return self::$cachedYtDlp;
        }

        // Check environment variable overrides (useful for AlwaysData / custom VPS)
        $envOverride = config($isFfmpeg ? 'media.ffmpeg_path' : 'media.yt_dlp_path');
        if (! empty($envOverride) && file_exists($envOverride)) {
            if ($isFfmpeg) {
                self::$cachedFfmpeg = $envOverride;
            } else {
                self::$cachedYtDlp = $envOverride;
            }

            return $envOverride;
        }

        // Check system PATH
        foreach ($binaryNames as $name) {
            $command = (DIRECTORY_SEPARATOR === '\\') ? "where {$name} 2>NUL" : "which {$name} 2>/dev/null";
            $output = @shell_exec($command);
            if (! empty($output)) {
                $lines = explode("\n", trim($output));
                $path = trim($lines[0]);
                if (file_exists($path)) {
                    if ($isFfmpeg) {
                        self::$cachedFfmpeg = $path;
                    } else {
                        self::$cachedYtDlp = $path;
                    }

                    return $path;
                }
            }
        }

        // Check common user-level install directories on shared Linux hosting (e.g. AlwaysData ~/.local/bin)
        $homeDir = getenv('HOME') ?: ($_SERVER['HOME'] ?? '');
        $candidatePaths = $isFfmpeg ? [
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg',
            $homeDir.'/.local/bin/ffmpeg',
            $homeDir.'/bin/ffmpeg',
        ] : [
            '/usr/bin/yt-dlp',
            '/usr/local/bin/yt-dlp',
            $homeDir.'/.local/bin/yt-dlp',
            $homeDir.'/bin/yt-dlp',
        ];

        foreach ($candidatePaths as $candidate) {
            if (! empty($candidate) && file_exists($candidate) && is_file($candidate)) {
                if ($isFfmpeg) {
                    self::$cachedFfmpeg = $candidate;
                } else {
                    self::$cachedYtDlp = $candidate;
                }

                return $candidate;
            }
        }

        if ($isFfmpeg) {
            self::$cachedFfmpeg = '';
        }
        if (! $isFfmpeg) {
            self::$cachedYtDlp = '';
        }

        return null;
    }

    protected function formatBytes(int $bytes): string
    {
        return $bytes >= 1048576 ? number_format($bytes / 1048576, 1).' MB' : number_format($bytes / 1024, 1).' KB';
    }
}
