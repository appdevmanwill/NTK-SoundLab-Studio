"""Loopback regression tests using only synthetic data and a scratch directory."""

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == '__main__':
    unittest.main()
