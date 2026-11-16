"""Loopback regression tests using only synthetic data and a scratch directory."""

import http.client
import io
import json
import re
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.parse

import soundlab_helper
from local_server import SESSION_HEADER, create_server
from suno_helper import LocalProxyHandler


class LocalHelperTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        self.working = base / 'working'
        (self.working / 'helper').mkdir(parents=True)
        (self.working / 'index.html').write_text('<!doctype html><title>Fixture</title>', encoding='utf-8')
        self.legacy = self.working / 'helper' / 'user_cookies.txt'
        self.legacy.write_bytes(b'legacy-canary')
        self.private = base / 'config' / 'user_cookies.txt'
        self.previous_private = base / 'old-config' / 'user_cookies.txt'
        locations = {
            'COOKIE_FILE_PATH': self.private,
            'PREVIOUS_PRIVATE_COOKIE_FILE': self.previous_private,
            'LEGACY_COOKIE_FILE': self.legacy,
        }
        for name, value in locations.items():
            patcher = patch.object(soundlab_helper, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def start(self, handler):
        server = create_server(handler, 0, self.working)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_port
        self.origin = f'http://127.0.0.1:{self.port}'

    def request(self, method, path, headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            connection.request(method, path, headers=headers or {}, body=body)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_cookie_read_write_requires_same_origin_session(self):
        self.start(soundlab_helper.SoundLabHTTPHandler)
        route = '/api/omni/cookies'
        payload = json.dumps({'cookies': 'new-canary'})
        foreign = {'Host': 'foreign.example', 'Origin': 'https://foreign.example'}
        self.assertEqual(self.request('GET', '/helper/user_cookies.txt', foreign)[0], 403)
        self.assertEqual(self.request('GET', '/helper/user_cookies.txt')[0], 404)
        self.assertEqual(self.request('HEAD', '/helper/user_cookies.txt')[0], 404)
        self.assertEqual(self.request('POST', route, {'Origin': self.origin, 'Content-Type': 'application/json'}, payload)[0], 401)
        self.assertFalse(self.private.exists())

        status, headers, _ = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly; SameSite=Strict', headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('POST', route, {'Cookie': cookie, 'Origin': 'https://foreign.example'}, payload)[0], 403)
        self.assertEqual(self.request('POST', route, {'Cookie': cookie, 'Origin': self.origin, 'Content-Type': 'text/plain'}, payload)[0], 403)
        self.assertEqual(self.request('POST', route, {'Cookie': cookie, 'Origin': self.origin, 'Content-Type': 'application/json'}, payload)[0], 200)
        self.assertEqual(self.private.read_bytes(), b'new-canary')
        self.assertEqual(self.legacy.read_bytes(), b'legacy-canary')
        self.assertNotIn('nocheckcertificate', soundlab_helper.get_ytdl_base_opts())

    def test_companion_session_is_scoped_and_both_helpers_guard_apis(self):
        for handler in (soundlab_helper.SoundLabHTTPHandler, LocalProxyHandler):
            with self.subTest(handler=handler):
                self.start(handler)
                trusted = {'Origin': 'http://127.0.0.1:47831', 'Sec-Fetch-Site': 'same-site'}
                self.assertEqual(self.request('GET', '/api/local-session', {'Origin': 'https://foreign.example'})[0], 403)
                self.assertEqual(self.request('GET', '/api/health', trusted)[0], 401)
                status, headers, body = self.request('GET', '/api/local-session', trusted)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Access-Control-Allow-Origin'], trusted['Origin'])
                authenticated = {**trusted, SESSION_HEADER: json.loads(body)['session']}
                with patch.object(soundlab_helper, 'check_demucs_available', return_value={'available': False}):
                    self.assertEqual(self.request('GET', '/api/health', authenticated)[0], 200)
                self.assertEqual(self.request('POST', '/api/omni/cookies', authenticated, '{}')[0], 403 if handler is soundlab_helper.SoundLabHTTPHandler else 404)

    def test_legacy_copy_never_replaces_existing_private_data(self):
        soundlab_helper.copy_legacy_cookies()
        self.assertEqual(self.private.read_bytes(), b'legacy-canary')
        self.private.write_bytes(b'new-canary')
        soundlab_helper.copy_legacy_cookies()
        self.assertEqual(self.private.read_bytes(), b'new-canary')

    def test_private_copy_prefers_the_previous_private_file(self):
        self.previous_private.parent.mkdir()
        self.previous_private.write_bytes(b'private-canary')
        soundlab_helper.copy_legacy_cookies()
        self.assertEqual(self.private.read_bytes(), b'private-canary')
        self.assertEqual(self.previous_private.read_bytes(), b'private-canary')
        self.assertEqual(self.legacy.read_bytes(), b'legacy-canary')

    def test_format_entry_sanitizes_query_uuid_and_resolves_acemusic_and_audiomack(self):
        entry = soundlab_helper._format_entry({
            'id': 'd3wxbtudvpih?sh=hcCYFakWHxi-1',
            'title': 'Query ID Track',
            'webpage_url': 'https://example.org/watch?v=1',
            'extractor_key': 'Generic',
            'formats': [],
        })
        self.assertRegex(entry['uuid'], r'^[a-zA-Z0-9_-]{1,160}$')

        html_page = (
            '<!doctype html><html><head>'
            '<meta property="og:title" content="Skyline Echo by Nova AI | ACE Music">'
            '<meta name="description" content="Ambient synth">'
            '<meta property="og:audio" content="/data/so_skyline.mp3">'
            '<meta property="og:image" content="/data/co_skyline.jpg">'
            '</head></html>'
        ).encode('utf-8')

        class _FakeResp(io.BytesIO):
            def __init__(self, data, url, ctype, status=200):
                super().__init__(data)
                self._url = url
                self.headers = {'Content-Type': ctype, 'Content-Length': str(len(data))}
                self.status = status
            def geturl(self):
                return self._url
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def fake_open(target_url, allow_subdomains=False, extra_headers=None, timeout=20):
            if target_url == 'https://acemusic.ai/song/d3wxbtudvpih':
                return _FakeResp(html_page, target_url, 'text/html; charset=utf-8')
            if target_url == 'https://acemusic.ai/data/so_skyline.mp3':
                return _FakeResp(b'ID3MP3', target_url, 'audio/mpeg')
            if target_url == 'https://acemusic.ai/data/co_skyline.jpg':
                return _FakeResp(b'JPGDATA', target_url, 'image/jpeg')
            raise AssertionError(f'Unexpected URL: {target_url}')

        orig_getaddrinfo = socket.getaddrinfo
        def selective_getaddrinfo(host, port, *args, **kwargs):
            if str(host).lower().endswith('acemusic.ai'):
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port or 443))]
            return orig_getaddrinfo(host, port, *args, **kwargs)

        self.start(soundlab_helper.SoundLabHTTPHandler)
        status, headers, _ = self.request('GET', '/')
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        auth = {'Cookie': cookie, 'Origin': self.origin}

        with patch.object(soundlab_helper.socket, 'getaddrinfo', side_effect=selective_getaddrinfo), \
             patch.object(soundlab_helper, '_open_acemusic_url', side_effect=fake_open):
            st, _, body = self.request(
                'GET',
                '/api/omni/resolve?url=' + urllib.parse.quote('https://acemusic.ai/song/d3wxbtudvpih?sh=hcCYFakWHxi', safe=''),
                auth,
            )
            self.assertEqual(st, 200, body)
            resolved = json.loads(body)
            self.assertEqual(resolved['uuid'], 'acemusic-d3wxbtudvpih')
            self.assertEqual(resolved['streamUrl'], '/api/acemusic/stream/d3wxbtudvpih')
            self.assertEqual(resolved['title'], 'Skyline Echo')
            self.assertEqual(resolved['artist'], 'Nova AI')

            st_audio, hdr_audio, audio_body = self.request('GET', resolved['streamUrl'], auth)
            self.assertEqual(st_audio, 200)
            self.assertEqual(hdr_audio['Content-Type'], 'audio/mpeg')
            self.assertEqual(audio_body, b'ID3MP3')

            st_cov, _, cov_body = self.request('GET', resolved['imageLarge'], auth)
            self.assertEqual(st_cov, 200)
            self.assertEqual(cov_body, b'JPGDATA')

        # Private DNS targets must be rejected even for acemusic subdomains; R2 asset redirects are allowed on public IPs
        private_addr = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch.object(soundlab_helper.socket, 'getaddrinfo', return_value=private_addr):
            with self.assertRaises(ValueError):
                soundlab_helper._assert_public_acemusic_url('https://acemusic.ai/data/so_skyline.mp3')
        with patch.object(soundlab_helper.socket, 'getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 443))]):
            soundlab_helper._assert_public_acemusic_url('https://demo.r2.cloudflarestorage.com/acemusic-data-prod/so_skyline.mp3', allow_subdomains=True)
            with self.assertRaises(ValueError):
                soundlab_helper._assert_public_acemusic_url('https://unrelated.example/so_skyline.mp3', allow_subdomains=True)

        # Audiomack returns honest 422 when legacy endpoint fails
        fake_ytdl = MagicMock()
        fake_ytdl.__enter__.return_value.extract_info.side_effect = RuntimeError('Failed to parse JSON')
        with patch.object(soundlab_helper, 'yt_dlp', MagicMock(YoutubeDL=MagicMock(return_value=fake_ytdl))):
            st_am, _, body_am = self.request(
                'GET',
                '/api/omni/resolve?url=' + urllib.parse.quote('https://audiomack.com/artist/song/track', safe=''),
                auth,
            )
            self.assertEqual(st_am, 422)
            self.assertIn('OAuth', body_am.decode('utf-8'))
            self.assertIn('Media Grabber', body_am.decode('utf-8'))

        st_dl, _, body_dl = self.request(
            'POST',
            '/api/omni/download',
            {**auth, 'Content-Type': 'application/json'},
            json.dumps({'url': 'https://audiomack.com/artist/song/track', 'is_audio_only': True}),
        )
        self.assertEqual(st_dl, 422)
        self.assertIn('OAuth', body_dl.decode('utf-8'))

    def test_download_task_falls_back_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / 'Track_123.m4a'
            out_file.write_bytes(b'M4ADATA')
            fake_ydl_instance = MagicMock()
            fake_ydl_instance.extract_info.return_value = {'id': '123', 'title': 'Track', 'ext': 'm4a'}
            fake_ydl_instance.prepare_filename.return_value = str(out_file)
            captured_opts = {}

            def _make_ydl(opts):
                captured_opts.update(opts)
                ctx = MagicMock()
                ctx.__enter__.return_value = fake_ydl_instance
                ctx.__exit__.return_value = False
                return ctx

            with patch.object(soundlab_helper.shutil, 'which', return_value=None), \
                 patch.object(soundlab_helper, 'yt_dlp', MagicMock(YoutubeDL=MagicMock(side_effect=_make_ydl))):
                soundlab_helper.download_media_task('job-no-ffmpeg', 'https://example.org/v', 'mp3', True, tmpdir)

            self.assertNotIn('postprocessors', captured_opts)
            self.assertEqual(soundlab_helper.JOBS['job-no-ffmpeg']['status'], 'complete')
            self.assertEqual(soundlab_helper.JOBS['job-no-ffmpeg']['filePath'], str(out_file))

    def test_uuid_not_hijacked_and_new_providers_supported(self):
        # 1. UUIDs on non-Suno sites must NEVER be treated as Suno URLs
        self.assertTrue(soundlab_helper.is_suno_url('00032777-30b1-482a-8e3f-d3fd44169009'))
        self.assertTrue(soundlab_helper.is_suno_url('https://suno.com/song/00032777-30b1-482a-8e3f-d3fd44169009'))
        self.assertFalse(soundlab_helper.is_suno_url('https://www.flowmusic.app/song/00032777-30b1-482a-8e3f-d3fd44169009'))
        self.assertFalse(soundlab_helper.is_suno_url('https://treblo.com/song/1b794faa-ad4f-483a-af70-93de2322937a'))
        self.assertFalse(soundlab_helper.is_suno_url('https://cdn.example.com/tracks/1b794faa-ad4f-483a-af70-93de2322937a.mp3'))

        # 2. Single-stream yt-dlp entries (e.g. Audius) must report hasAudio=True and proper platform label
        audius_entry = soundlab_helper._format_entry({
            'id': 'V4W8r',
            'title': 'HYPERMANTRA',
            'uploader': 'camoufly',
            'webpage_url': 'https://audius.co/camouflybeats/hypermantra-86216',
            'url': 'https://api.audius.co/v1/tracks/V4W8r/stream',
            'ext': 'mp3',
            'acodec': 'mp3',
            'vcodec': None,
            'extractor_key': 'Audius',
            'formats': [],
        })
        self.assertTrue(audius_entry['hasAudio'])
        self.assertFalse(audius_entry['hasVideo'])
        self.assertEqual(audius_entry['platform'], 'Audius')

        mixcloud_entry = soundlab_helper._format_entry({
            'id': 'mix-1',
            'title': 'Party Mix',
            'webpage_url': 'https://www.mixcloud.com/spartacus/party-time/',
            'extractor_key': 'Mixcloud',
            'formats': [{'format_id': 'm4a', 'ext': 'm4a', 'vcodec': 'none', 'acodec': 'mp4a.40.2'}],
        })
        self.assertEqual(mixcloud_entry['platform'], 'Mixcloud')
        self.assertTrue(mixcloud_entry['hasAudio'])

        # 3. Vocaroo URL CDN selection matches official bundle rule
        self.assertEqual(soundlab_helper.vocaroo_media_url('123456789012'), 'https://media1.vocaroo.com/mp3/123456789012')
        self.assertEqual(soundlab_helper.vocaroo_media_url('1234567890'), 'https://media1.vocaroo.com/mp3/1234567890')
        self.assertEqual(soundlab_helper.vocaroo_media_url('abcdefghijk'), 'https://media.vocaroo.com/mp3/abcdefghijk')

        class _MockResp(io.BytesIO):
            def __init__(self, data, url, ctype='text/html; charset=utf-8', status=200):
                super().__init__(data)
                self._url = url
                self.headers = {'Content-Type': ctype, 'Content-Length': str(len(data))}
                self.status = status
            def geturl(self):
                return self._url
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        flow_html = (
            '<!doctype html><html><head>'
            '<meta property="og:title" content="Sunset Beat by ProducerOne | Flow Music">'
            '<meta property="og:audio" content="https://storage.googleapis.com/producer-app-public/clips/00032777-30b1-482a-8e3f-d3fd44169009.m4a">'
            '<meta property="og:image" content="https://storage.googleapis.com/producer-app-public/assets/cover1.jpg">'
            '</head></html>'
        ).encode('utf-8')
        treblo_html = (
            '<!doctype html><html><head>'
            '<meta property="og:title" content="Midnight Synth | Treblo">'
            '<meta property="og:audio" content="https://cdn.treblo.com/generations3/audio_9fc6.ogg">'
            '<meta property="og:image" content="https://scdn.treblo.com/cover.jpg">'
            '</head></html>'
        ).encode('utf-8')
        audius_json = json.dumps({
            'data': {
                'id': 'V4W8r',
                'title': 'HYPERMANTRA',
                'duration': 180,
                'genre': 'Electronic',
                'user': {'name': 'camoufly'},
                'artwork': {'480x480': 'https://creatornode.audius.co/art.jpg'},
            }
        }).encode('utf-8')

        def fake_open_public(target_url, host_checker=None, label='Media', extra_headers=None, timeout=20, method=None):
            if target_url == 'https://www.flowmusic.app/song/00032777-30b1-482a-8e3f-d3fd44169009':
                return _MockResp(flow_html, target_url)
            if target_url == 'https://storage.googleapis.com/producer-app-public/clips/00032777-30b1-482a-8e3f-d3fd44169009.m4a':
                return _MockResp(b'M4ABYTES', target_url, 'audio/mp4')
            if target_url == 'https://treblo.com/song/1b794faa-ad4f-483a-af70-93de2322937a':
                return _MockResp(treblo_html, target_url)
            if target_url == 'https://cdn.treblo.com/generations3/audio_9fc6.ogg':
                return _MockResp(b'OggS', target_url, 'audio/ogg')
            if 'api.audius.co/v1/resolve' in target_url or target_url == 'https://api.audius.co/v1/tracks/V4W8r':
                return _MockResp(audius_json, target_url, 'application/json')
            if target_url == 'https://api.audius.co/v1/tracks/V4W8r/stream':
                return _MockResp(b'AUDIUSMP3', target_url, 'audio/mpeg')
            if target_url == 'https://media1.vocaroo.com/mp3/123456789012':
                return _MockResp(b'VOCMP3', target_url, 'audio/mpeg')
            if target_url == 'https://studio-api.prod.suno.com/api/clip/00032777-30b1-482a-8e3f-d3fd44169009':
                return _MockResp(b'{"id":"00032777-30b1-482a-8e3f-d3fd44169009"}', target_url, 'application/json')
            raise AssertionError(f'Unexpected URL: {target_url}')

        orig_getaddrinfo = socket.getaddrinfo
        def selective_public_dns(host, port, *args, **kwargs):
            if str(host) in ('127.0.0.1', 'localhost', '::1'):
                return orig_getaddrinfo(host, port, *args, **kwargs)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', port or 443))]

        self.start(soundlab_helper.SoundLabHTTPHandler)
        status, headers, _ = self.request('GET', '/')
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        auth = {'Cookie': cookie, 'Origin': self.origin}

        with patch.object(soundlab_helper.socket, 'getaddrinfo', side_effect=selective_public_dns), \
             patch.object(soundlab_helper, '_open_public_url', side_effect=fake_open_public):
            # Flow Music (via riffusion.com alias!)
            st_f, _, body_f = self.request('GET', '/api/omni/resolve?url=' + urllib.parse.quote('https://www.riffusion.com/song/00032777-30b1-482a-8e3f-d3fd44169009', safe=''), auth)
            self.assertEqual(st_f, 200, body_f)
            rf = json.loads(body_f)
            self.assertEqual(rf['platform'], 'Flow Music')
            self.assertEqual(rf['streamUrl'], '/api/flowmusic/stream/00032777-30b1-482a-8e3f-d3fd44169009')
            st_fa, _, body_fa = self.request('GET', rf['streamUrl'], auth)
            self.assertEqual(st_fa, 200)
            self.assertEqual(body_fa, b'M4ABYTES')

            # Treblo (via sonauto.ai alias!)
            st_t, _, body_t = self.request('GET', '/api/omni/resolve?url=' + urllib.parse.quote('https://sonauto.ai/song/1b794faa-ad4f-483a-af70-93de2322937a', safe=''), auth)
            self.assertEqual(st_t, 200, body_t)
            rt = json.loads(body_t)
            self.assertEqual(rt['platform'], 'Treblo')
            self.assertEqual(rt['streamUrl'], '/api/treblo/stream/1b794faa-ad4f-483a-af70-93de2322937a')
            st_ta, _, body_ta = self.request('GET', rt['streamUrl'], auth)
            self.assertEqual(st_ta, 200)
            self.assertEqual(body_ta, b'OggS')

            # Audius native + stream proxy
            st_au, _, body_au = self.request('GET', '/api/omni/resolve?url=' + urllib.parse.quote('https://audius.co/camouflybeats/hypermantra-86216', safe=''), auth)
            self.assertEqual(st_au, 200, body_au)
            rau = json.loads(body_au)
            self.assertEqual(rau['platform'], 'Audius')
            self.assertEqual(rau['streamUrl'], '/api/audius/stream/V4W8r')
            st_aus, _, body_aus = self.request('GET', rau['streamUrl'], auth)
            self.assertEqual(st_aus, 200)
            self.assertEqual(body_aus, b'AUDIUSMP3')

            # Vocaroo native + stream proxy
            st_v, _, body_v = self.request('GET', '/api/omni/resolve?url=' + urllib.parse.quote('https://voca.ro/123456789012', safe=''), auth)
            self.assertEqual(st_v, 200, body_v)
            rv = json.loads(body_v)
            self.assertEqual(rv['platform'], 'Vocaroo')
            self.assertEqual(rv['streamUrl'], '/api/vocaroo/stream/123456789012')
            st_vs, _, body_vs = self.request('GET', rv['streamUrl'], auth)
            self.assertEqual(st_vs, 200)
            self.assertEqual(body_vs, b'VOCMP3')

            # Suno route parity in soundlab_helper.py
            st_su, _, body_su = self.request('GET', '/api/suno/song/00032777-30b1-482a-8e3f-d3fd44169009', auth)
            self.assertEqual(st_su, 200, body_su)

        # DRM platforms return honest 422
        for drm_url in ('https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT', 'https://music.apple.com/us/album/x/1?i=2', 'https://www.deezer.com/track/3135556'):
            st_d, _, body_d = self.request('GET', '/api/omni/resolve?url=' + urllib.parse.quote(drm_url, safe=''), auth)
            self.assertEqual(st_d, 422, body_d)
            self.assertIn('DRM', body_d.decode('utf-8'))

        # yt-dlp extractor bug/login errors return clean 422 instead of 500
        bad_ytdl = MagicMock()
        bad_ytdl.__enter__.return_value.extract_info.side_effect = TypeError("'bool' object is not subscriptable")
        with patch.object(soundlab_helper, 'yt_dlp', MagicMock(YoutubeDL=MagicMock(return_value=bad_ytdl))):
            st_j, _, body_j = self.request('GET', '/api/omni/resolve?url=' + urllib.parse.quote('https://www.jamendo.com/track/123/test', safe=''), auth)
            self.assertEqual(st_j, 422, body_j)


if __name__ == '__main__':
    unittest.main()
