"""Shared loopback and static asset boundary for the optional helpers."""

import argparse
import hmac
import json
import mimetypes
import secrets
from functools import partial
from http.cookies import CookieError, SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


STUDIO_ROOT = Path(__file__).resolve().parent.parent
SESSION_COOKIE = 'ntk_helper_session'
SESSION_HEADER = 'X-NTK-Helper-Session'
LOCAL_APP_ORIGINS = frozenset({
    'http://127.0.0.1:47831',
    'http://127.0.0.1:5000',
    'http://127.0.0.1:8000',
})
ROOT_ASSETS = frozenset({'index.html', '404.html', 'manifest.json', 'sw.js', 'robots.txt', 'LICENSE', 'THIRD_PARTY_NOTICES.md'})
ASSET_TYPES = {
    'assets': {'.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2'},
    'css': {'.css'},
    'js': {'.js'},
    'lib': {'.js', '.mjs', '.wasm', '.txt', '.json'},
}


class StudioHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript', '.mjs': 'text/javascript', '.wasm': 'application/wasm'}
    timeout = 30

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
            pass

    def log_request(self, code='-', size='-'):
        # Query strings can contain signed media URLs.
        self.log_message('%s %s %s', self.command, urlsplit(self.path).path, code)

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/') else 'no-cache')
        if getattr(self, 'trusted_origin', None):
            self.send_header('Access-Control-Allow-Origin', self.trusted_origin)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Expose-Headers', 'Content-Length, Content-Range, Content-Disposition')
        super().end_headers()

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _guard(self):
        self.trusted_origin = None
        self.entry_session = False
        hosts = self.headers.get_all('Host') or []
        port = self.server.server_port
        hosts_allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if port == 80:
            hosts_allowed.update({'127.0.0.1', 'localhost'})
        if len(hosts) != 1 or hosts[0].lower() not in hosts_allowed:
            self._send_json(403, {'error': 'Unexpected local helper host.'})
            return False
        self.same_origin = f'http://{hosts[0].lower()}'
        origin = self.headers.get('Origin')
        site = self.headers.get('Sec-Fetch-Site')
        if origin != self.same_origin and origin in LOCAL_APP_ORIGINS and self.path.startswith('/api/'):
            self.trusted_origin = origin
        elif (origin and origin != self.same_origin) or site not in (None, 'none', 'same-origin'):
            self._send_json(403, {'error': 'This origin cannot access the local helper.'})
            return False
        return True

    def _has_cookie(self):
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', '')).get(SESSION_COOKIE)
        except CookieError:
            return False
        return bool(cookie and hmac.compare_digest(cookie.value.encode(), self.server.session.encode()))

    def _api_session(self):
        if self.trusted_origin:
            token = self.headers.get(SESSION_HEADER, '')
            allowed = hmac.compare_digest(token.encode(), self.server.companion_session.encode())
        else:
            allowed = self._has_cookie()
        if not allowed:
            self._send_json(401, {'error': 'Open the local helper page or reconnect the studio first.'})
        return allowed

    def _serve_asset(self, head=False):
        path = unquote(urlsplit(self.path).path)
        relative = PurePosixPath(path.lstrip('/') or 'index.html')
        root = Path(self.directory).resolve()
        file = root.joinpath(*relative.parts)
        allowed = relative.as_posix() in ROOT_ASSETS or (
            len(relative.parts) > 1 and relative.suffix.lower() in ASSET_TYPES.get(relative.parts[0], ())
        )
        if relative.as_posix() == 'models/htdemucs_embedded.onnx':
            allowed = True
        if not allowed or '\\' in path or any(part.startswith('.') for part in relative.parts) or file.resolve() != file or not file.is_file():
            self.send_error(404, 'Studio asset not found')
            return
        if relative.name.lower() in {'user_cookies.txt', 'cookies.txt', 'cookies.json', 'credentials.json', 'auth.json'}:
            self.send_error(404, 'Studio asset not found')
            return
        if not head and relative.as_posix() == 'index.html':
            self.entry_session = True
        if head:
            super().do_HEAD()
        else:
            super().do_GET()

    def send_response(self, code, message=None):
        super().send_response(code, message)
        if code == 200 and getattr(self, 'entry_session', False):
            self.send_header('Set-Cookie', f'{SESSION_COOKIE}={self.server.session}; Path=/api; HttpOnly; SameSite=Strict')

    def do_GET(self):
        if not self._guard():
            return
        path = urlsplit(self.path).path
        if path == '/api/local-session':
            if self.trusted_origin:
                self._send_json(200, {'session': self.server.companion_session})
            else:
                self._send_json(403, {'error': 'This origin cannot open a companion session.'})
        elif path.startswith('/api/') or path == '/health':
            if self._api_session():
                self.handle_api_get()
        else:
            self._serve_asset()

    def do_HEAD(self):
        if self._guard():
            self._serve_asset(head=True)

    def do_OPTIONS(self):
        if not self._guard():
            return
        if not self.trusted_origin:
            self._send_json(403, {'error': 'Unexpected local helper preflight.'})
            return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', f'Content-Type, {SESSION_HEADER}, X-Song-Id')
        if self.headers.get('Access-Control-Request-Private-Network') == 'true':
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def do_POST(self):
        if self._guard() and self._api_session():
            self.handle_api_post()

    def handle_api_get(self):
        self._send_json(404, {'error': 'Endpoint not found.'})

    def handle_api_post(self):
        self._send_json(404, {'error': 'Endpoint not found.'})

    def read_body(self, maximum):
        try:
            length = int(self.headers.get('Content-Length', ''))
        except ValueError:
            length = -1
        if self.headers.get('Transfer-Encoding') or length < 0:
            self._send_json(400, {'error': 'A valid Content-Length is required.'})
            return None
        if length > maximum:
            self._send_json(413, {'error': 'The request is larger than the local helper limit.'})
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._send_json(400, {'error': 'The request ended early.'})
            return None
        return body


def create_server(handler, port, directory):
    mimetypes.add_type('application/onnx', '.onnx')
    server = ThreadingHTTPServer(('127.0.0.1', port), partial(handler, directory=str(directory)))
    server.session = secrets.token_urlsafe(32)
    server.companion_session = secrets.token_urlsafe(32)
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Serve only SoundLab frontend assets on loopback.')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--dir', type=Path, default=STUDIO_ROOT)
    args = parser.parse_args()
    with create_server(StudioHandler, args.port, args.dir) as server:
        print(f'NTK SoundLab Studio at http://127.0.0.1:{server.server_port}/')
        server.serve_forever()
