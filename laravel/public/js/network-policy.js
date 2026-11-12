export function isLoopbackHost(hostname) {
  const host = String(hostname).toLowerCase().replace(/\.$/, '');
  return host === 'localhost' || host.endsWith('.localhost') || /^127(?:\.\d{1,3}){3}$/.test(host) || host === '[::1]' || /^\[::ffff:7f[0-9a-f]{2}:[0-9a-f]{1,4}\]$/.test(host);
}

export function canUseLocalHelper() {
  const loc = globalThis.location;
  return !!loc && (loc.protocol === 'file:' || isLoopbackHost(loc.hostname));
}

// A hosted page must never probe or upload to a visitor's local helper implicitly.
export async function fetch(input, options = {}) {
  const { timeoutMs = 60000, ...requestOptions } = options;
  const raw = typeof input === 'string' ? input : input.url;
  const url = new URL(raw, globalThis.location?.href || 'http://localhost/');
  if (isLoopbackHost(url.hostname) && !canUseLocalHelper()) {
    throw new Error('This hosted version cannot contact a local helper. Use its configured server or open the desktop app.');
  }
  const timeout = AbortSignal.timeout(Math.max(1000, Math.min(300000, timeoutMs)));
  const signal = requestOptions.signal ? AbortSignal.any([requestOptions.signal, timeout]) : timeout;
  if (url.hostname === '127.0.0.1' && url.port === '8899' && url.pathname.startsWith('/api/') && url.origin !== globalThis.location?.origin) {
    const reply = await globalThis.fetch(new URL('/api/local-session', url), { signal, cache: 'no-store' });
    if (!reply.ok) throw new Error('Open the local helper page to use its tools.');
    const { session } = await reply.json();
    if (typeof session !== 'string' || !session) throw new Error('The local helper did not establish a session.');
    const headers = new Headers(requestOptions.headers ?? input.headers);
    headers.set('X-NTK-Helper-Session', session);
    return globalThis.fetch(input, { ...requestOptions, headers, signal });
  }
  return globalThis.fetch(input, { ...requestOptions, signal });
}
