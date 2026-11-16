package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/subtle"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"html"
	"io"
	"io/fs"
	"log"
	"mime"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"os"
	"os/signal"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

// Assets are populated from an explicit production allowlist by build.ps1.
//
//go:embed all:assets/*
var embeddedAssets embed.FS

const defaultPort = 47831
const maxJSON = 2 << 20
const sessionCookie = "ntk_desktop_session"

var uuidRE = regexp.MustCompile(`(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`)
var aceIDRE = regexp.MustCompile(`^[a-zA-Z0-9_-]{4,64}$`)
var aceLocaleRE = regexp.MustCompile(`^[a-zA-Z-]{2,8}$`)
var vocarooIDRE = regexp.MustCompile(`^[a-zA-Z0-9_-]{6,24}$`)
var audiusIDRE = regexp.MustCompile(`^[a-zA-Z0-9_-]{3,32}$`)
var metaTagRE = regexp.MustCompile(`(?is)<meta\s+[^>]+>`)
var attrRE = regexp.MustCompile(`(?is)([a-zA-Z_:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')`)
var audioTagRE = regexp.MustCompile(`(?is)<audio\b[^>]*\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')`)

type config struct {
	port           int
	dataDir        string
	headless       bool
	idleTimeout    time.Duration
	startupTimeout time.Duration
}

type desktopApp struct {
	assets        fs.FS
	client        *http.Client
	host          string
	token         string
	modelDirs     []string
	mu            sync.Mutex
	lastHeartbeat time.Time
	started       time.Time
	connected     bool
}

func init() {
	for ext, kind := range map[string]string{".js": "application/javascript; charset=utf-8", ".mjs": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".wasm": "application/wasm", ".json": "application/json", ".svg": "image/svg+xml", ".onnx": "application/octet-stream", ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac", ".ogg": "audio/ogg", ".opus": "audio/opus"} {
		_ = mime.AddExtensionType(ext, kind)
	}
}

func newToken() (string, error) {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	return hex.EncodeToString(b[:]), nil
}

func fileExists(p string) bool { s, err := os.Stat(p); return err == nil && s.Mode().IsRegular() }

// Resolve once and dial a checked IP, preventing DNS rebinding at connection time.
func publicIP(ip netip.Addr) bool {
	ip = ip.Unmap()
	if !ip.IsValid() || !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() {
		return false
	}
	for _, cidr := range []string{"0.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4", "::/96", "64:ff9b::/96", "64:ff9b:1::/48", "100::/64", "2001::/32", "2001:db8::/32", "2002::/16", "fc00::/7", "fe80::/10"} {
		if netip.MustParsePrefix(cidr).Contains(ip) {
			return false
		}
	}
	return true
}

func validateURL(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)
	if err != nil || u == nil || u.Hostname() == "" || u.User != nil || (u.Scheme != "https" && u.Scheme != "http") || strings.ContainsAny(raw, "\\\r\n") {
		return nil, errors.New("a public HTTP or HTTPS URL is required")
	}
	if port := u.Port(); port != "" && !((u.Scheme == "https" && port == "443") || (u.Scheme == "http" && port == "80")) {
		return nil, errors.New("only standard HTTP and HTTPS ports are allowed")
	}
	h := strings.ToLower(strings.TrimSuffix(u.Hostname(), "."))
	if h == "localhost" || strings.HasSuffix(h, ".localhost") || strings.HasSuffix(h, ".local") || !strings.Contains(h, ".") && !strings.Contains(h, ":") {
		return nil, errors.New("local destinations are not allowed")
	}
	if ip, err := netip.ParseAddr(h); err == nil && !publicIP(ip) {
		return nil, errors.New("private or reserved destinations are not allowed")
	}
	return u, nil
}

type lookupFunc func(context.Context, string) ([]net.IPAddr, error)

func publicDialer(lookup lookupFunc) func(context.Context, string, string) (net.Conn, error) {
	return func(ctx context.Context, network, address string) (net.Conn, error) {
		host, port, err := net.SplitHostPort(address)
		if err != nil || (port != "80" && port != "443") {
			return nil, errors.New("destination port blocked")
		}
		ips, err := lookup(ctx, host)
		if err != nil || len(ips) == 0 {
			return nil, errors.New("destination DNS lookup failed")
		}
		for _, ip := range ips {
			addr, ok := netip.AddrFromSlice(ip.IP)
			if !ok || !publicIP(addr) {
				return nil, errors.New("destination DNS resolved to a private or reserved address")
			}
		}
		dialer := net.Dialer{Timeout: 10 * time.Second, KeepAlive: 30 * time.Second}
		var last error
		for _, ip := range ips {
			conn, err := dialer.DialContext(ctx, network, net.JoinHostPort(ip.IP.String(), port))
			if err == nil {
				return conn, nil
			}
			last = err
		}
		return nil, last
	}
}

func safeClient() *http.Client {
	transport := &http.Transport{Proxy: nil, DialContext: publicDialer(net.DefaultResolver.LookupIPAddr), TLSHandshakeTimeout: 10 * time.Second, ResponseHeaderTimeout: 20 * time.Second, MaxIdleConns: 16, IdleConnTimeout: 30 * time.Second}
	return &http.Client{Transport: transport, Timeout: 90 * time.Second, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return errors.New("too many redirects")
		}
		if len(via) > 0 && via[len(via)-1].URL.Scheme == "https" && req.URL.Scheme != "https" {
			return errors.New("insecure media redirect blocked")
		}
		_, err := validateURL(req.URL.String())
		return err
	}}
}

func providerClient(base *http.Client, host string) *http.Client {
	client := *base
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if req.URL.Scheme != "https" || !strings.EqualFold(req.URL.Hostname(), host) {
			return errors.New("provider redirect blocked")
		}
		if base.CheckRedirect != nil {
			return base.CheckRedirect(req, via)
		}
		return nil
	}
	return &client
}

func jsonResponse(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func apiError(w http.ResponseWriter, status int, message string) {
	jsonResponse(w, status, map[string]any{"success": false, "error": message})
}

func method(w http.ResponseWriter, r *http.Request, methods ...string) bool {
	for _, m := range methods {
		if r.Method == m {
			return true
		}
	}
	w.Header().Set("Allow", strings.Join(methods, ", "))
	apiError(w, http.StatusMethodNotAllowed, "Method not allowed")
	return false
}

func decodeJSON(w http.ResponseWriter, r *http.Request, dst any) bool {
	r.Body = http.MaxBytesReader(w, r.Body, maxJSON)
	dec := json.NewDecoder(r.Body)
	if err := dec.Decode(dst); err != nil {
		apiError(w, http.StatusBadRequest, "Invalid or oversized JSON body")
		return false
	}
	if err := dec.Decode(&struct{}{}); err != io.EOF {
		apiError(w, http.StatusBadRequest, "Expected one JSON object")
		return false
	}
	return true
}

func (a *desktopApp) touch() {
	a.mu.Lock()
	a.lastHeartbeat = time.Now()
	a.connected = true
	a.mu.Unlock()
}
func (a *desktopApp) expired(now time.Time, idle, startup time.Duration) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	if !a.connected {
		return now.Sub(a.started) > startup
	}
	return now.Sub(a.lastHeartbeat) > idle
}

// The entry page establishes a random HttpOnly session. APIs require that
// session and matching Host/Origin. Cross-site bootstrap is blocked as well.
func (a *desktopApp) secure(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Cross-Origin-Opener-Policy", "same-origin")
		w.Header().Set("Cross-Origin-Embedder-Policy", "credentialless")
		if r.Host != a.host {
			apiError(w, http.StatusForbidden, "Unexpected host")
			return
		}
		if origin := r.Header.Get("Origin"); origin != "" && origin != "http://"+a.host {
			apiError(w, http.StatusForbidden, "Cross-origin requests are blocked")
			return
		}
		if site := r.Header.Get("Sec-Fetch-Site"); site != "" && site != "none" && site != "same-origin" {
			apiError(w, http.StatusForbidden, "Cross-site requests are blocked")
			return
		}
		if strings.Contains(r.URL.Path, "\\") {
			apiError(w, http.StatusBadRequest, "Invalid path")
			return
		}
		for _, part := range strings.Split(r.URL.Path, "/") {
			if part == ".." || part == "." {
				apiError(w, http.StatusBadRequest, "Invalid path")
				return
			}
		}
		isEntry := r.URL.Path == "/" || r.URL.Path == "/index.html"
		cookie, err := r.Cookie(sessionCookie)
		authed := err == nil && subtle.ConstantTimeCompare([]byte(cookie.Value), []byte(a.token)) == 1
		if isEntry && (r.Method == "GET" || r.Method == "HEAD") {
			http.SetCookie(w, &http.Cookie{Name: sessionCookie, Value: a.token, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode})
		} else if !authed {
			apiError(w, http.StatusUnauthorized, "Open the desktop application before making requests")
			return
		}
		next.ServeHTTP(w, r)
	})
}

func (a *desktopApp) request(ctx context.Context, method, target string, body io.Reader) (*http.Response, error) {
	if _, err := validateURL(target); err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, method, target, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	client := a.client
	if req.URL.Hostname() == "studio-api.prod.suno.com" {
		client = providerClient(client, req.URL.Hostname())
	}
	return client.Do(req)
}

func (a *desktopApp) proxyJSON(w http.ResponseWriter, r *http.Request, method, target string, body io.Reader) {
	resp, err := a.request(r.Context(), method, target, body)
	if err != nil {
		apiError(w, http.StatusBadGateway, "Could not reach the public provider")
		return
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(io.LimitReader(resp.Body, maxJSON+1))
	if err != nil || len(b) > maxJSON || !json.Valid(b) {
		apiError(w, http.StatusBadGateway, "Provider returned invalid or oversized JSON")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(resp.StatusCode)
	_, _ = w.Write(b)
}

func sunoHost(h string) bool {
	h = strings.ToLower(h)
	return h == "suno.com" || h == "www.suno.com" || h == "suno.ai" || h == "www.suno.ai"
}
func sunoID(raw string) string {
	if uuidRE.MatchString(raw) {
		return strings.ToLower(raw)
	}
	u, err := validateURL(raw)
	if err != nil || !sunoHost(u.Hostname()) {
		return ""
	}
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) == 2 && parts[0] == "song" && uuidRE.MatchString(parts[1]) {
		return strings.ToLower(parts[1])
	}
	return ""
}

func (a *desktopApp) resolveSuno(ctx context.Context, raw string) (string, error) {
	if id := sunoID(raw); id != "" {
		return id, nil
	}
	u, err := validateURL(raw)
	if err != nil || u.Scheme != "https" || !sunoHost(u.Hostname()) || !strings.HasPrefix(u.Path, "/s/") {
		return "", errors.New("a Suno song URL, shortlink or UUID is required")
	}
	client := *a.client
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 || req.URL.Scheme != "https" || !sunoHost(req.URL.Hostname()) {
			return errors.New("Suno redirect destination blocked")
		}
		_, err := validateURL(req.URL.String())
		return err
	}
	req, _ := http.NewRequestWithContext(ctx, "GET", u.String(), nil)
	resp, err := client.Do(req)
	if err != nil {
		return "", errors.New("could not resolve the Suno shortlink")
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", errors.New("Suno shortlink is unavailable")
	}
	id := sunoID(resp.Request.URL.String())
	if id == "" {
		return "", errors.New("Suno shortlink did not resolve to a song")
	}
	return id, nil
}

type ogProvider struct {
	key          string
	name         string
	pageHosts    []string
	cdnHosts     []string
	cdnSuffixes  []string
	stripSuffix  []string
	canonicalFmt string
}

var ogProviders = []ogProvider{
	{
		key:          "acemusic",
		name:         "ACE Music",
		pageHosts:    []string{"acemusic.ai", "www.acemusic.ai"},
		cdnSuffixes:  []string{".acemusic.ai", ".r2.cloudflarestorage.com", ".r2.dev"},
		stripSuffix:  []string{" | ACE Music", " - ACE Music"},
		canonicalFmt: "https://acemusic.ai/song/%s",
	},
	{
		key:          "flowmusic",
		name:         "Flow Music",
		pageHosts:    []string{"flowmusic.app", "www.flowmusic.app", "riffusion.com", "www.riffusion.com", "producer.ai", "www.producer.ai"},
		cdnHosts:     []string{"storage.googleapis.com"},
		cdnSuffixes:  []string{".flowmusic.app", ".riffusion.com", ".producer.ai"},
		stripSuffix:  []string{" | Flow Music", " - Flow Music", " | Riffusion", " - Riffusion", " | Producer.ai", " - Producer.ai"},
		canonicalFmt: "https://www.flowmusic.app/song/%s",
	},
	{
		key:          "treblo",
		name:         "Treblo",
		pageHosts:    []string{"treblo.com", "www.treblo.com", "sonauto.ai", "www.sonauto.ai"},
		cdnSuffixes:  []string{".treblo.com", ".sonauto.ai", ".r2.cloudflarestorage.com"},
		stripSuffix:  []string{" | Treblo", " - Treblo", " | Sonauto", " - Sonauto"},
		canonicalFmt: "https://treblo.com/song/%s",
	},
}

func hostMatches(h, domain string) bool {
	h = strings.ToLower(strings.TrimSuffix(h, "."))
	domain = strings.ToLower(strings.TrimSuffix(domain, "."))
	return h != "" && domain != "" && (h == domain || strings.HasSuffix(h, "."+domain))
}

func (p ogProvider) matchPageHost(h string) bool {
	h = strings.ToLower(strings.TrimSuffix(h, "."))
	for _, ph := range p.pageHosts {
		if h == ph {
			return true
		}
	}
	return false
}

func (p ogProvider) matchAssetHost(h string) bool {
	h = strings.ToLower(strings.TrimSuffix(h, "."))
	if p.matchPageHost(h) {
		return true
	}
	for _, ch := range p.cdnHosts {
		if h == ch {
			return true
		}
	}
	for _, sfx := range p.cdnSuffixes {
		if strings.HasSuffix(h, sfx) {
			return true
		}
	}
	return false
}

func ogProviderForHost(h string) (ogProvider, bool) {
	for _, p := range ogProviders {
		if p.matchPageHost(h) {
			return p, true
		}
	}
	return ogProvider{}, false
}

func ogProviderByKey(key string) (ogProvider, bool) {
	for _, p := range ogProviders {
		if p.key == key {
			return p, true
		}
	}
	return ogProvider{}, false
}

func aceMusicHost(h string) bool {
	p, ok := ogProviderByKey("acemusic")
	return ok && p.matchPageHost(h)
}

func aceMusicAssetHost(h string) bool {
	p, ok := ogProviderByKey("acemusic")
	return ok && p.matchAssetHost(h)
}

func drmPlatformForHost(h string) string {
	h = strings.ToLower(strings.TrimSuffix(h, "."))
	if strings.HasPrefix(h, "music.amazon.") {
		return "Amazon Music"
	}
	for _, pair := range [][2]string{
		{"audiomack.com", "Audiomack"},
		{"spotify.com", "Spotify"},
		{"music.apple.com", "Apple Music"},
		{"itunes.apple.com", "Apple Music"},
		{"tidal.com", "Tidal"},
		{"deezer.com", "Deezer"},
		{"pandora.com", "Pandora"},
		{"boomplay.com", "Boomplay"},
	} {
		if hostMatches(h, pair[0]) {
			return pair[1]
		}
	}
	return ""
}

func drmPlatformMessage(platform string) string {
	if platform == "Audiomack" {
		return "Audiomack requires signed OAuth playback credentials and does not expose public audio streams to SoundLab. Use Audiomack directly or import a local MP3/WAV/FLAC/M4A file into SoundLab Studio."
	}
	return platform + " streams are DRM-protected and require an official " + platform + " session/license. SoundLab Studio cannot extract DRM-encrypted tracks from " + platform + "; please import a local MP3/WAV/FLAC/M4A file instead."
}

func (p ogProvider) extractSongID(raw string) string {
	if aceIDRE.MatchString(raw) {
		return raw
	}
	u, err := validateURL(raw)
	if err != nil || u.Scheme != "https" || !p.matchPageHost(u.Hostname()) {
		return ""
	}
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) == 2 && (parts[0] == "song" || parts[0] == "songs") && aceIDRE.MatchString(parts[1]) {
		return parts[1]
	}
	if len(parts) == 3 && aceLocaleRE.MatchString(parts[0]) && (parts[1] == "song" || parts[1] == "songs") && aceIDRE.MatchString(parts[2]) {
		return parts[2]
	}
	return ""
}

func aceMusicID(raw string) string {
	p, _ := ogProviderByKey("acemusic")
	return p.extractSongID(raw)
}

func aceMusicClient(base *http.Client, allowSubdomains bool) *http.Client {
	p, _ := ogProviderByKey("acemusic")
	return ogProviderClient(base, p, allowSubdomains)
}

func ogProviderClient(base *http.Client, p ogProvider, allowSubdomains bool) *http.Client {
	client := *base
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		hostOK := p.matchPageHost(req.URL.Hostname())
		if allowSubdomains {
			hostOK = p.matchAssetHost(req.URL.Hostname())
		}
		if len(via) >= 5 || req.URL.Scheme != "https" || !hostOK {
			return errors.New(p.name + " redirect blocked")
		}
		if _, err := validateURL(req.URL.String()); err != nil {
			return err
		}
		if base.CheckRedirect != nil {
			return base.CheckRedirect(req, via)
		}
		return nil
	}
	return &client
}

func safePublicHTTPSClient(base *http.Client, allowedHost func(string) bool) *http.Client {
	client := *base
	client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if len(via) >= 6 || req.URL.Scheme != "https" {
			return errors.New("media redirect blocked")
		}
		if allowedHost != nil && !allowedHost(req.URL.Hostname()) {
			return errors.New("media redirect host not permitted")
		}
		if _, err := validateURL(req.URL.String()); err != nil {
			return err
		}
		if base.CheckRedirect != nil {
			return base.CheckRedirect(req, via)
		}
		return nil
	}
	return &client
}

func extractMetaAttr(body, targetKey string) string {
	for _, tag := range metaTagRE.FindAllString(body, -1) {
		var key, content string
		for _, m := range attrRE.FindAllStringSubmatch(tag, -1) {
			attrName := strings.ToLower(m[1])
			val := m[2]
			if val == "" {
				val = m[3]
			}
			switch attrName {
			case "property", "name":
				key = strings.ToLower(strings.TrimSpace(val))
			case "content":
				content = html.UnescapeString(strings.TrimSpace(val))
			}
		}
		if key == strings.ToLower(targetKey) && content != "" {
			return content
		}
	}
	return ""
}

func extractAudioSrc(body string) string {
	m := audioTagRE.FindStringSubmatch(body)
	if len(m) < 3 {
		return ""
	}
	if m[1] != "" {
		return html.UnescapeString(strings.TrimSpace(m[1]))
	}
	return html.UnescapeString(strings.TrimSpace(m[2]))
}

func splitProviderTitleAndArtist(rawTitle, fallbackID, providerName string, stripSuffixes []string) (string, string) {
	cleaned := strings.TrimSpace(rawTitle)
	for _, suffix := range stripSuffixes {
		cleaned = strings.TrimSpace(strings.TrimSuffix(cleaned, suffix))
	}
	for _, sep := range []string{" by ", " par "} {
		if idx := strings.LastIndex(cleaned, sep); idx > 0 {
			title := strings.TrimSpace(cleaned[:idx])
			artist := strings.TrimSpace(cleaned[idx+len(sep):])
			if title != "" && artist != "" {
				return title, artist
			}
		}
	}
	if cleaned == "" {
		shortID := fallbackID
		if len(shortID) > 16 {
			shortID = shortID[:8]
		}
		return providerName + "_" + shortID, providerName
	}
	return cleaned, providerName
}

func (a *desktopApp) resolveOGProvider(ctx context.Context, p ogProvider, raw string) (map[string]any, string, string, int, error) {
	id := p.extractSongID(raw)
	if id == "" {
		return nil, "", "", 400, errors.New("a valid " + p.name + " song link is required")
	}
	pageURL := fmt.Sprintf(p.canonicalFmt, id)
	req, err := http.NewRequestWithContext(ctx, "GET", pageURL, nil)
	if err != nil {
		return nil, "", "", 400, err
	}
	req.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
	resp, err := ogProviderClient(a.client, p, false).Do(req)
	if err != nil {
		return nil, "", "", 502, errors.New("could not reach " + p.name)
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		code := resp.StatusCode
		if code < 400 || code >= 600 {
			code = 502
		}
		return nil, "", "", code, errors.New(p.name + " song page is unavailable")
	}
	kind, _, _ := mime.ParseMediaType(resp.Header.Get("Content-Type"))
	if kind != "" && kind != "text/html" && kind != "application/xhtml+xml" {
		return nil, "", "", 502, errors.New(p.name + " returned an unexpected response type")
	}
	bodyBytes, err := io.ReadAll(io.LimitReader(resp.Body, maxJSON+1))
	if err != nil || len(bodyBytes) > maxJSON {
		return nil, "", "", 502, errors.New(p.name + " returned an unreadable or oversized page")
	}
	htmlBody := string(bodyBytes)
	audioRaw := extractMetaAttr(htmlBody, "og:audio")
	if audioRaw == "" {
		audioRaw = extractAudioSrc(htmlBody)
	}
	if audioRaw == "" {
		return nil, "", "", 422, errors.New(p.name + " did not expose a public audio stream for this link")
	}
	baseURL := resp.Request.URL
	if baseURL == nil {
		baseURL, _ = url.Parse(pageURL)
	}
	resolvedAudio, err := baseURL.Parse(audioRaw)
	if err != nil {
		return nil, "", "", 502, errors.New(p.name + " returned an invalid audio URL")
	}
	audioURL, err := validateURL(resolvedAudio.String())
	if err != nil || audioURL.Scheme != "https" || !p.matchAssetHost(audioURL.Hostname()) {
		return nil, "", "", 502, errors.New(p.name + " returned an unsupported audio destination")
	}
	var coverURL string
	if imgRaw := extractMetaAttr(htmlBody, "og:image"); imgRaw != "" {
		if resolvedImg, err := baseURL.Parse(imgRaw); err == nil {
			if validImg, err := validateURL(resolvedImg.String()); err == nil && validImg.Scheme == "https" && p.matchAssetHost(validImg.Hostname()) {
				coverURL = validImg.String()
			}
		}
	}
	title, artist := splitProviderTitleAndArtist(extractMetaAttr(htmlBody, "og:title"), id, p.name, p.stripSuffix)
	desc := extractMetaAttr(htmlBody, "description")
	if desc == "" {
		desc = extractMetaAttr(htmlBody, "og:description")
	}
	coverProxy := ""
	if coverURL != "" {
		coverProxy = "/api/" + p.key + "/cover/" + id
	}
	normID := strings.ToLower(id)
	finalPage := pageURL
	if baseURL != nil && baseURL.String() != "" {
		finalPage = baseURL.String()
	}
	meta := map[string]any{
		"type":       "single",
		"uuid":       p.key + "-" + normID,
		"id":         normID,
		"title":      title,
		"artist":     artist,
		"duration":   0,
		"imageLarge": coverProxy,
		"imageThumb": coverProxy,
		"streamUrl":  "/api/" + p.key + "/stream/" + id,
		"url":        finalPage,
		"platform":   p.name,
		"hasVideo":   false,
		"hasAudio":   true,
		"hasStem":    true,
		"tags":       p.name + " • " + artist,
		"prompt":     desc,
	}
	return meta, audioURL.String(), coverURL, 200, nil
}

type audiusArtwork struct {
	W1000   string   `json:"1000x1000"`
	W480    string   `json:"480x480"`
	W150    string   `json:"150x150"`
	Mirrors []string `json:"mirrors"`
}

func (a audiusArtwork) best() string {
	if a.W1000 != "" {
		return a.W1000
	}
	if a.W480 != "" {
		return a.W480
	}
	return a.W150
}

func (a audiusArtwork) candidates() []string {
	primary := a.best()
	parsed, err := validateURL(primary)
	if err != nil || parsed.Scheme != "https" {
		return nil
	}
	out := []string{parsed.String()}
	seen := map[string]bool{parsed.String(): true}
	suffix := parsed.RequestURI()
	for _, m := range a.Mirrors {
		mu, merr := validateURL(strings.TrimSpace(m))
		if merr != nil || mu.Scheme != "https" {
			continue
		}
		alt := "https://" + mu.Host + suffix
		if !seen[alt] {
			seen[alt] = true
			out = append(out, alt)
			if len(out) >= 4 {
				break
			}
		}
	}
	return out
}

type audiusTrack struct {
	ID          string        `json:"id"`
	Title       string        `json:"title"`
	Duration    float64       `json:"duration"`
	Genre       string        `json:"genre"`
	Description string        `json:"description"`
	Permalink   string        `json:"permalink"`
	Artwork     audiusArtwork `json:"artwork"`
	User        struct {
		Name   string `json:"name"`
		Handle string `json:"handle"`
	} `json:"user"`
}

func formatAudiusTrackMap(t audiusTrack, webpageURL string) map[string]any {
	artist := strings.TrimSpace(t.User.Name)
	if artist == "" {
		artist = strings.TrimSpace(t.User.Handle)
	}
	if artist == "" {
		artist = "Audius Creator"
	}
	coverProxy := ""
	if t.Artwork.best() != "" {
		coverProxy = "/api/audius/cover/" + t.ID
	}
	title := strings.TrimSpace(t.Title)
	if title == "" {
		title = "Audius_" + t.ID
	}
	genre := strings.TrimSpace(t.Genre)
	if genre == "" {
		genre = "Audius"
	}
	page := webpageURL
	if page == "" && t.Permalink != "" {
		page = "https://audius.co" + t.Permalink
	}
	return map[string]any{
		"uuid":       "audius-" + strings.ToLower(t.ID),
		"id":         t.ID,
		"title":      title,
		"artist":     artist,
		"duration":   int(t.Duration),
		"imageLarge": coverProxy,
		"imageThumb": coverProxy,
		"streamUrl":  "/api/audius/stream/" + t.ID,
		"url":        page,
		"platform":   "Audius",
		"hasVideo":   false,
		"hasAudio":   true,
		"hasStem":    true,
		"tags":       "Audius • " + genre + " • " + artist,
		"prompt":     t.Description,
	}
}

func (a *desktopApp) resolveAudius(ctx context.Context, rawURL string) (map[string]any, int, error) {
	apiURL := "https://api.audius.co/v1/resolve?url=" + url.QueryEscape(rawURL)
	req, err := http.NewRequestWithContext(ctx, "GET", apiURL, nil)
	if err != nil {
		return nil, 400, err
	}
	req.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
	req.Header.Set("Accept", "application/json")
	resp, err := providerClient(a.client, "api.audius.co").Do(req)
	if err != nil {
		return nil, 502, errors.New("could not reach Audius API")
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, 422, fmt.Errorf("Audius API returned HTTP %d", resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxJSON))
	if err != nil {
		return nil, 502, errors.New("Audius returned an unreadable response")
	}
	var env struct {
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &env); err != nil || len(env.Data) == 0 {
		return nil, 502, errors.New("Audius returned invalid metadata")
	}
	var single audiusTrack
	if err := json.Unmarshal(env.Data, &single); err == nil && audiusIDRE.MatchString(single.ID) && single.Title != "" {
		out := formatAudiusTrackMap(single, rawURL)
		out["type"] = "single"
		return out, 200, nil
	}
	var playlist struct {
		ID           string        `json:"id"`
		PlaylistName string        `json:"playlist_name"`
		User         struct{ Name string `json:"name"` } `json:"user"`
		Tracks       []audiusTrack `json:"tracks"`
	}
	if err := json.Unmarshal(env.Data, &playlist); err == nil && len(playlist.Tracks) > 0 {
		var clips []map[string]any
		for _, t := range playlist.Tracks {
			if audiusIDRE.MatchString(t.ID) {
				clips = append(clips, formatAudiusTrackMap(t, ""))
			}
		}
		if len(clips) > 0 {
			name := strings.TrimSpace(playlist.PlaylistName)
			if name == "" {
				name = "Audius Playlist"
			}
			return map[string]any{
				"type":     "playlist",
				"id":       playlist.ID,
				"title":    name,
				"uploader": playlist.User.Name,
				"count":    len(clips),
				"clips":    clips,
			}, 200, nil
		}
	}
	var arr []audiusTrack
	if err := json.Unmarshal(env.Data, &arr); err == nil && len(arr) > 0 {
		var clips []map[string]any
		for _, t := range arr {
			if audiusIDRE.MatchString(t.ID) {
				clips = append(clips, formatAudiusTrackMap(t, ""))
			}
		}
		if len(clips) > 0 {
			return map[string]any{
				"type":     "playlist",
				"id":       clips[0]["id"],
				"title":    "Audius Playlist",
				"uploader": clips[0]["artist"],
				"count":    len(clips),
				"clips":    clips,
			}, 200, nil
		}
	}
	return nil, 422, errors.New("Audius did not return a playable track for this link")
}

func vocarooID(raw string) string {
	if vocarooIDRE.MatchString(raw) {
		return raw
	}
	u, err := validateURL(raw)
	if err != nil || (!hostMatches(u.Hostname(), "vocaroo.com") && !hostMatches(u.Hostname(), "voca.ro")) {
		return ""
	}
	parts := strings.Split(strings.Trim(u.Path, "/"), "/")
	if len(parts) == 1 && vocarooIDRE.MatchString(parts[0]) {
		return parts[0]
	}
	if len(parts) == 2 && (parts[0] == "embed" || parts[0] == "i") && vocarooIDRE.MatchString(parts[1]) {
		return parts[1]
	}
	return ""
}

func vocarooMP3URL(id string) string {
	sub := "media"
	if len(id) == 10 || (len(id) == 12 && strings.HasPrefix(id, "1")) {
		sub = "media1"
	}
	return "https://" + sub + ".vocaroo.com/mp3/" + id
}

func vocarooHostAllowed(h string) bool {
	h = strings.ToLower(strings.TrimSuffix(h, "."))
	return h == "media.vocaroo.com" || h == "media1.vocaroo.com"
}

func (a *desktopApp) resolveVocaroo(ctx context.Context, raw string) (map[string]any, int, error) {
	id := vocarooID(raw)
	if id == "" {
		return nil, 400, errors.New("a valid Vocaroo recording link is required")
	}
	mp3URL := vocarooMP3URL(id)
	client := safePublicHTTPSClient(a.client, vocarooHostAllowed)
	req, _ := http.NewRequestWithContext(ctx, "HEAD", mp3URL, nil)
	req.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
	resp, err := client.Do(req)
	if err == nil && (resp.StatusCode == http.StatusMethodNotAllowed || resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusNotImplemented) {
		resp.Body.Close()
		req2, _ := http.NewRequestWithContext(ctx, "GET", mp3URL, nil)
		req2.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
		req2.Header.Set("Range", "bytes=0-0")
		resp, err = client.Do(req2)
	}
	if err != nil {
		return nil, 502, errors.New("could not reach Vocaroo media CDN")
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound || resp.StatusCode == http.StatusGone {
		return nil, 422, errors.New("Vocaroo recording was not found or has expired")
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, 422, fmt.Errorf("Vocaroo media CDN returned HTTP %d", resp.StatusCode)
	}
	return map[string]any{
		"type":       "single",
		"uuid":       "vocaroo-" + strings.ToLower(id),
		"id":         id,
		"title":      "Vocaroo_" + id,
		"artist":     "Vocaroo Voice Recording",
		"duration":   0,
		"imageLarge": "",
		"imageThumb": "",
		"streamUrl":  "/api/vocaroo/stream/" + id,
		"url":        "https://vocaroo.com/" + id,
		"platform":   "Vocaroo",
		"hasVideo":   false,
		"hasAudio":   true,
		"hasStem":    true,
		"tags":       "Vocaroo • Voice Note",
	}, 200, nil
}

func isDirectMediaExt(ext string) bool {
	switch strings.ToLower(ext) {
	case ".mp3", ".wav", ".m4a", ".aac", ".mp4", ".flac", ".ogg", ".opus", ".webm":
		return true
	}
	return false
}

var explicitMediaMimes = map[string]bool{
	"audio/mpeg":      true,
	"audio/mp3":       true,
	"audio/mp4":       true,
	"audio/m4a":       true,
	"audio/x-m4a":     true,
	"audio/aac":       true,
	"audio/x-aac":     true,
	"audio/aacp":      true,
	"audio/wav":       true,
	"audio/x-wav":     true,
	"audio/wave":      true,
	"audio/ogg":       true,
	"audio/opus":      true,
	"audio/flac":      true,
	"audio/x-flac":    true,
	"audio/webm":      true,
	"video/mp4":       true,
	"video/webm":      true,
	"video/quicktime": true,
	"application/ogg": true,
}

var audioStreamMimes = map[string]bool{
	"audio/mpeg":               true,
	"audio/mp3":                true,
	"audio/mp4":                true,
	"audio/m4a":                true,
	"audio/x-m4a":              true,
	"audio/aac":                true,
	"audio/x-aac":              true,
	"audio/aacp":               true,
	"audio/wav":                true,
	"audio/x-wav":              true,
	"audio/wave":               true,
	"audio/ogg":                true,
	"audio/opus":               true,
	"audio/flac":               true,
	"audio/x-flac":             true,
	"audio/webm":               true,
	"video/mp4":                true,
	"video/webm":               true,
	"video/quicktime":          true,
	"application/ogg":          true,
	"application/octet-stream": true,
	"binary/octet-stream":      true,
}

var imageCoverMimes = map[string]bool{
	"image/jpeg": true,
	"image/jpg":  true,
	"image/png":  true,
	"image/webp": true,
	"image/gif":  true,
}

func (a *desktopApp) proxyValidatedMedia(w http.ResponseWriter, r *http.Request, client *http.Client, targetURL string, allowedMimes map[string]bool, forceMime string, maxBytes int64) {
	req, err := http.NewRequestWithContext(r.Context(), r.Method, targetURL, nil)
	if err != nil {
		apiError(w, 400, "Invalid media URL")
		return
	}
	req.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
	if rangeHeader := r.Header.Get("Range"); rangeHeader != "" {
		if !regexp.MustCompile(`^bytes=[0-9]*-[0-9]*$`).MatchString(rangeHeader) {
			apiError(w, 400, "Only a single byte range is supported")
			return
		}
		req.Header.Set("Range", rangeHeader)
	}
	resp, err := client.Do(req)
	if err != nil {
		apiError(w, 502, "Could not reach the media provider")
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 && resp.StatusCode != 206 {
		apiError(w, resp.StatusCode, "Audio provider could not supply this track")
		return
	}
	if resp.ContentLength > maxBytes {
		apiError(w, 502, "Media exceeds the desktop streaming limit")
		return
	}
	kind, _, _ := mime.ParseMediaType(resp.Header.Get("Content-Type"))
	if !allowedMimes[kind] {
		apiError(w, 502, "The audio provider returned an unexpected content type")
		return
	}
	outType := forceMime
	if outType == "" {
		if kind == "" || kind == "application/octet-stream" || kind == "binary/octet-stream" {
			if guessed := mime.TypeByExtension(strings.ToLower(path.Ext(req.URL.Path))); guessed != "" {
				outType = guessed
			} else {
				outType = "application/octet-stream"
			}
		} else {
			outType = kind
		}
	}
	w.Header().Set("Content-Type", outType)
	w.Header().Set("Cache-Control", "no-store")
	for _, h := range []string{"Content-Length", "Content-Range", "Accept-Ranges"} {
		if v := resp.Header.Get(h); v != "" {
			w.Header().Set(h, v)
		}
	}
	w.WriteHeader(resp.StatusCode)
	if r.Method != "HEAD" {
		_, _ = io.Copy(w, io.LimitReader(resp.Body, maxBytes))
	}
}

func (a *desktopApp) routes() http.Handler {
	mux := http.NewServeMux()
	status := func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET") {
			return
		}
		jsonResponse(w, 200, map[string]any{"status": "ok", "mode": "desktop-native", "version": "2026.11.16.2", "persistent_origin": true})
	}
	mux.HandleFunc("/api/desktop/status", status)
	mux.HandleFunc("/api/health", status)
	mux.HandleFunc("/api/desktop/heartbeat", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "POST") {
			return
		}
		a.touch()
		w.WriteHeader(http.StatusNoContent)
	})
	// No unload shutdown endpoint: navigation/reload cannot terminate the backend.
	mux.HandleFunc("/api/capabilities", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET") {
			return
		}
		jsonResponse(w, 200, map[string]any{"server": "NTK SoundLab Desktop", "mode": "standalone-native", "yt_dlp": false, "ffmpeg": false, "download_jobs": false, "suno_drm": true, "demucs": map[string]any{"available": false, "engine": "Browser engine requires compatible model weights", "local_model": a.modelPath("htdemucs_embedded.onnx") != ""}})
	})
	mux.HandleFunc("/api/mango/rights", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "POST") {
			return
		}
		var p struct {
			ContentID     string `json:"content_id"`
			UUID          string `json:"uuid"`
			ContentParams struct {
				ContentID string `json:"content_id"`
			} `json:"content_params"`
		}
		if !decodeJSON(w, r, &p) {
			return
		}
		id := p.ContentParams.ContentID
		if id == "" {
			id = p.ContentID
		}
		if id == "" {
			id = p.UUID
		}
		if !uuidRE.MatchString(id) {
			apiError(w, 400, "A valid Suno UUID is required")
			return
		}
		b, _ := json.Marshal(map[string]any{"content_params": map[string]string{"content_id": strings.ToLower(id), "content_type": "clip"}})
		a.proxyJSON(w, r, "POST", "https://studio-api.prod.suno.com/api/mango/rights", bytes.NewReader(b))
	})
	for _, prefix := range []string{"/api/clip/", "/api/suno/song/", "/api/suno/clip/", "/api/playlist/", "/api/suno/playlist/"} {
		prefix := prefix
		mux.HandleFunc(prefix, func(w http.ResponseWriter, r *http.Request) {
			if !method(w, r, "GET") {
				return
			}
			id := strings.TrimPrefix(r.URL.Path, prefix)
			if !uuidRE.MatchString(id) {
				apiError(w, 400, "A valid Suno UUID is required")
				return
			}
			kind := "clip"
			if strings.Contains(prefix, "playlist") {
				kind = "playlist"
			}
			target := "https://studio-api.prod.suno.com/api/" + kind + "/" + strings.ToLower(id)
			if page := r.URL.Query().Get("page"); page != "" {
				if !regexp.MustCompile(`^[1-9][0-9]{0,3}$`).MatchString(page) {
					apiError(w, 400, "Invalid page")
					return
				}
				target += "/?page=" + page
			}
			a.proxyJSON(w, r, "GET", target, nil)
		})
	}
	mux.HandleFunc("/api/suno/unshorten", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET") {
			return
		}
		id, err := a.resolveSuno(r.Context(), r.URL.Query().Get("url"))
		if err != nil {
			apiError(w, 400, err.Error())
			return
		}
		jsonResponse(w, 200, map[string]any{"status": "ok", "uuid": id, "target_url": "https://suno.com/song/" + id})
	})
	mux.HandleFunc("/api/suno/stream/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		id := strings.TrimSuffix(strings.TrimPrefix(r.URL.Path, "/api/suno/stream/"), ".m4a")
		if !uuidRE.MatchString(id) {
			apiError(w, 400, "A valid Suno UUID is required")
			return
		}
		target := "https://d2lwuy8qc234o3.cloudfront.net/1/clip/" + strings.ToLower(id) + ".m4a"
		sunoMimes := map[string]bool{
			"audio/mp4":                true,
			"audio/m4a":                true,
			"audio/x-m4a":              true,
			"video/mp4":                true,
			"application/octet-stream": true,
			"binary/octet-stream":      true,
		}
		a.proxyValidatedMedia(w, r, providerClient(a.client, "d2lwuy8qc234o3.cloudfront.net"), target, sunoMimes, "audio/mp4", 512<<20)
	})
	for _, prov := range ogProviders {
		prov := prov
		mux.HandleFunc("/api/"+prov.key+"/stream/", func(w http.ResponseWriter, r *http.Request) {
			if !method(w, r, "GET", "HEAD") {
				return
			}
			id := strings.TrimPrefix(r.URL.Path, "/api/"+prov.key+"/stream/")
			for _, ext := range []string{".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".flac", ".webm"} {
				id = strings.TrimSuffix(id, ext)
			}
			if !aceIDRE.MatchString(id) {
				apiError(w, 400, "A valid "+prov.name+" song ID is required")
				return
			}
			_, audioURL, _, status, err := a.resolveOGProvider(r.Context(), prov, id)
			if err != nil {
				apiError(w, status, err.Error())
				return
			}
			a.proxyValidatedMedia(w, r, ogProviderClient(a.client, prov, true), audioURL, audioStreamMimes, "", 512<<20)
		})
		mux.HandleFunc("/api/"+prov.key+"/cover/", func(w http.ResponseWriter, r *http.Request) {
			if !method(w, r, "GET", "HEAD") {
				return
			}
			id := strings.TrimPrefix(r.URL.Path, "/api/"+prov.key+"/cover/")
			for _, ext := range []string{".jpg", ".jpeg", ".png", ".webp"} {
				id = strings.TrimSuffix(id, ext)
			}
			if !aceIDRE.MatchString(id) {
				apiError(w, 400, "A valid "+prov.name+" song ID is required")
				return
			}
			_, _, coverURL, status, err := a.resolveOGProvider(r.Context(), prov, id)
			if err != nil {
				apiError(w, status, err.Error())
				return
			}
			if coverURL == "" {
				apiError(w, 404, "No cover artwork is available for this "+prov.name+" track")
				return
			}
			a.proxyValidatedMedia(w, r, ogProviderClient(a.client, prov, true), coverURL, imageCoverMimes, "", 16<<20)
		})
	}
	mux.HandleFunc("/api/audius/stream/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/api/audius/stream/")
		for _, ext := range []string{".mp3", ".m4a"} {
			id = strings.TrimSuffix(id, ext)
		}
		if !audiusIDRE.MatchString(id) {
			apiError(w, 400, "A valid Audius track ID is required")
			return
		}
		target := "https://api.audius.co/v1/tracks/" + id + "/stream"
		a.proxyValidatedMedia(w, r, safePublicHTTPSClient(a.client, nil), target, audioStreamMimes, "", 512<<20)
	})
	mux.HandleFunc("/api/audius/cover/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/api/audius/cover/")
		for _, ext := range []string{".jpg", ".jpeg", ".png", ".webp"} {
			id = strings.TrimSuffix(id, ext)
		}
		if !audiusIDRE.MatchString(id) {
			apiError(w, 400, "A valid Audius track ID is required")
			return
		}
		req, _ := http.NewRequestWithContext(r.Context(), "GET", "https://api.audius.co/v1/tracks/"+id, nil)
		req.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
		req.Header.Set("Accept", "application/json")
		resp, err := providerClient(a.client, "api.audius.co").Do(req)
		if err != nil || resp.StatusCode != 200 {
			if resp != nil {
				resp.Body.Close()
			}
			apiError(w, 502, "Could not fetch Audius track artwork")
			return
		}
		defer resp.Body.Close()
		var env struct {
			Data audiusTrack `json:"data"`
		}
		if err := json.NewDecoder(io.LimitReader(resp.Body, maxJSON)).Decode(&env); err != nil {
			apiError(w, 502, "Invalid Audius artwork metadata")
			return
		}
		candidates := env.Data.Artwork.candidates()
		if len(candidates) == 0 {
			apiError(w, 404, "No cover artwork is available for this Audius track")
			return
		}
		coverClient := safePublicHTTPSClient(a.client, nil)
		chosen := candidates[0]
		if len(candidates) > 1 {
			for _, candidate := range candidates {
				if hreq, herr := http.NewRequestWithContext(r.Context(), "HEAD", candidate, nil); herr == nil {
					hreq.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
					if hresp, hdoErr := coverClient.Do(hreq); hdoErr == nil {
						_ = hresp.Body.Close()
						if hresp.StatusCode >= 200 && hresp.StatusCode < 300 {
							chosen = candidate
							break
						}
					}
				}
			}
		}
		a.proxyValidatedMedia(w, r, coverClient, chosen, imageCoverMimes, "", 16<<20)
	})
	mux.HandleFunc("/api/vocaroo/stream/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		id := strings.TrimPrefix(r.URL.Path, "/api/vocaroo/stream/")
		for _, ext := range []string{".mp3", ".ogg"} {
			id = strings.TrimSuffix(id, ext)
		}
		if !vocarooIDRE.MatchString(id) {
			apiError(w, 400, "A valid Vocaroo ID is required")
			return
		}
		a.proxyValidatedMedia(w, r, safePublicHTTPSClient(a.client, vocarooHostAllowed), vocarooMP3URL(id), audioStreamMimes, "audio/mpeg", 128<<20)
	})
	mux.HandleFunc("/api/omni/direct-stream", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		raw := strings.TrimSpace(r.URL.Query().Get("url"))
		u, err := validateURL(raw)
		if err != nil {
			apiError(w, 400, err.Error())
			return
		}
		ext := strings.ToLower(path.Ext(u.Path))
		isGrab := r.URL.Query().Get("grab") == "1"
		allowedMimes := audioStreamMimes
		if !isDirectMediaExt(ext) {
			if !isGrab || ext != "" {
				apiError(w, 422, "Only direct audio/video media files can be streamed through this endpoint")
				return
			}
			allowedMimes = explicitMediaMimes
		}
		client := *a.client
		baseCheck := a.client.CheckRedirect
		client.CheckRedirect = func(req *http.Request, via []*http.Request) error {
			if len(via) >= 5 {
				return errors.New("too many redirects")
			}
			if len(via) > 0 && via[len(via)-1].URL.Scheme == "https" && req.URL.Scheme != "https" {
				return errors.New("insecure media redirect blocked")
			}
			if _, err := validateURL(req.URL.String()); err != nil {
				return err
			}
			if baseCheck != nil {
				return baseCheck(req, via)
			}
			return nil
		}
		a.proxyValidatedMedia(w, r, &client, u.String(), allowedMimes, "", 512<<20)
	})
	mux.HandleFunc("/api/omni/resolve", a.resolveMedia)
	mux.HandleFunc("/api/omni/download", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "POST") {
			return
		}
		var p struct {
			URL       string `json:"url"`
			Format    string `json:"format"`
			AudioOnly bool   `json:"is_audio_only"`
		}
		if !decodeJSON(w, r, &p) {
			return
		}
		apiError(w, http.StatusNotImplemented, "Download conversion jobs are not supported by this portable build. Use Suno audio, a direct media URL, or import a local audio file. No download was started.")
	})
	mux.HandleFunc("/api/omni/status/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET") {
			return
		}
		apiError(w, 404, "No such download job exists")
	})
	mux.HandleFunc("/models/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		name := strings.TrimPrefix(r.URL.Path, "/models/")
		if name != "htdemucs_embedded.onnx" {
			http.NotFound(w, r)
			return
		}
		p := a.modelPath(name)
		if p == "" {
			http.NotFound(w, r)
			return
		}
		http.ServeFile(w, r, p)
	})
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if !method(w, r, "GET", "HEAD") {
			return
		}
		if strings.HasPrefix(r.URL.Path, "/api/") {
			apiError(w, 404, "Endpoint not found")
			return
		}
		name := strings.TrimPrefix(r.URL.Path, "/")
		if name == "" {
			name = "index.html"
		}
		if !fs.ValidPath(name) {
			http.NotFound(w, r)
			return
		}
		data, err := fs.ReadFile(a.assets, name)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Cache-Control", "no-cache")
		if contentType := mime.TypeByExtension(path.Ext(name)); contentType != "" {
			w.Header().Set("Content-Type", contentType)
		}
		http.ServeContent(w, r, name, time.Time{}, bytes.NewReader(data))
	})
	return a.secure(mux)
}

func (a *desktopApp) modelPath(name string) string {
	for _, dir := range a.modelDirs {
		p := filepath.Join(dir, name)
		if fileExists(p) {
			return p
		}
	}
	return ""
}

func (a *desktopApp) resolveMedia(w http.ResponseWriter, r *http.Request) {
	if !method(w, r, "GET") {
		return
	}
	raw := strings.TrimSpace(r.URL.Query().Get("url"))
	u, err := validateURL(raw)
	if err != nil {
		apiError(w, 400, err.Error())
		return
	}
	if drmPlat := drmPlatformForHost(u.Hostname()); drmPlat != "" {
		apiError(w, 422, drmPlatformMessage(drmPlat))
		return
	}
	if sunoHost(u.Hostname()) {
		id, err := a.resolveSuno(r.Context(), raw)
		if err != nil {
			apiError(w, 400, err.Error())
			return
		}
		a.proxyJSON(w, r, "GET", "https://studio-api.prod.suno.com/api/clip/"+id, nil)
		return
	}
	if prov, ok := ogProviderForHost(u.Hostname()); ok {
		meta, _, _, status, err := a.resolveOGProvider(r.Context(), prov, raw)
		if err != nil {
			apiError(w, status, err.Error())
			return
		}
		jsonResponse(w, 200, meta)
		return
	}
	if hostMatches(u.Hostname(), "audius.co") {
		meta, status, err := a.resolveAudius(r.Context(), raw)
		if err != nil {
			apiError(w, status, err.Error())
			return
		}
		jsonResponse(w, 200, meta)
		return
	}
	if hostMatches(u.Hostname(), "vocaroo.com") || hostMatches(u.Hostname(), "voca.ro") {
		meta, status, err := a.resolveVocaroo(r.Context(), raw)
		if err != nil {
			apiError(w, status, err.Error())
			return
		}
		jsonResponse(w, 200, meta)
		return
	}
	ext := strings.ToLower(path.Ext(u.Path))
	if ext == ".m3u8" || ext == ".mpd" {
		apiError(w, 422, "HLS/DASH playlist manifests (.m3u8/.mpd) require FFmpeg/yt-dlp remuxing. Start the local Python helper (OmniHelper) or import a local MP3/WAV/MP4 file instead.")
		return
	}
	if !isDirectMediaExt(ext) {
		apiError(w, 422, "This desktop build supports Suno AI, ACE Music, Flow Music (Riffusion), Treblo (Sonauto), Audius, Vocaroo, and direct media URLs (.mp3, .wav, .m4a, .aac, .flac, .ogg, .opus, .mp4, .webm). For YouTube/TikTok/SoundCloud/Bandcamp/Mixcloud, run the Python helper or import a local file.")
		return
	}
	resp, err := a.request(r.Context(), "HEAD", raw, nil)
	if err == nil && (resp.StatusCode == http.StatusMethodNotAllowed || resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusNotImplemented) {
		resp.Body.Close()
		probeReq, reqErr := http.NewRequestWithContext(r.Context(), "GET", raw, nil)
		if reqErr == nil {
			probeReq.Header.Set("User-Agent", "NTK-SoundLab-Studio/2026.11")
			probeReq.Header.Set("Range", "bytes=0-0")
			resp, err = a.client.Do(probeReq)
		}
	}
	if err != nil {
		apiError(w, 502, "Could not verify the public media URL")
		return
	}
	resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		apiError(w, 422, "The media URL is unavailable")
		return
	}
	streamTarget := raw
	if resp.Request != nil && resp.Request.URL != nil {
		streamTarget = resp.Request.URL.String()
	}
	if _, err := validateURL(streamTarget); err != nil {
		apiError(w, 502, "The media URL redirected to a blocked destination")
		return
	}
	id, err := newToken()
	if err != nil {
		apiError(w, 500, "Could not allocate a media identifier")
		return
	}
	id = "direct-" + id[:16]
	jsonResponse(w, 200, map[string]any{"type": "single", "uuid": id, "id": id, "title": strings.TrimSuffix(path.Base(u.Path), ext), "artist": "Direct Web Stream", "duration": 0, "imageLarge": "", "imageThumb": "", "streamUrl": "/api/omni/direct-stream?url=" + url.QueryEscape(streamTarget), "url": raw, "platform": "Direct Media File", "hasVideo": ext == ".mp4" || ext == ".webm", "hasAudio": true, "hasStem": false, "tags": strings.ToUpper(strings.TrimPrefix(ext, ".")) + " Stream"})
}

func run(cfg config) error {
	if cfg.port < 1 || cfg.port > 65535 {
		return errors.New("port must be between 1 and 65535; the desktop origin must remain stable")
	}
	if cfg.idleTimeout < 10*time.Second || cfg.startupTimeout < 10*time.Second {
		return errors.New("lifecycle timeouts must be at least 10 seconds")
	}
	if err := os.MkdirAll(cfg.dataDir, 0700); err != nil {
		return fmt.Errorf("data directory is not writable: %w", err)
	}
	logFile, err := os.OpenFile(filepath.Join(cfg.dataDir, "desktop.log"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return fmt.Errorf("data directory is not writable: %w", err)
	}
	defer logFile.Close()
	log.SetOutput(io.MultiWriter(os.Stderr, logFile))
	listener, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", cfg.port))
	if err != nil {
		return fmt.Errorf("desktop port %d is unavailable; close the other instance and retry. The app will not switch ports and hide your saved data: %w", cfg.port, err)
	}
	defer listener.Close()
	assets, err := fs.Sub(embeddedAssets, "assets")
	if err != nil {
		return err
	}
	token, err := newToken()
	if err != nil {
		return err
	}
	exe, _ := os.Executable()
	a := &desktopApp{assets: assets, client: safeClient(), host: listener.Addr().String(), token: token, modelDirs: []string{filepath.Join(cfg.dataDir, "models"), filepath.Join(filepath.Dir(exe), "models")}, started: time.Now(), lastHeartbeat: time.Now()}
	server := &http.Server{Handler: a.routes(), ReadHeaderTimeout: 10 * time.Second, ReadTimeout: 30 * time.Second, WriteTimeout: 120 * time.Second, IdleTimeout: 30 * time.Second, MaxHeaderBytes: 16 << 10}
	serverErr := make(chan error, 1)
	go func() { serverErr <- server.Serve(listener) }()
	defer server.Close()
	appURL := "http://" + a.host
	if cfg.headless {
		fmt.Printf("{\"url\":%q,\"mode\":\"headless\"}\n", appURL)
	} else if err := launchBrowser(appURL, cfg.dataDir); err != nil {
		return err
	}
	log.Printf("Desktop ready at %s (stable origin; prior browser profiles retained)", appURL)
	signalCh := make(chan os.Signal, 1)
	signal.Notify(signalCh, os.Interrupt)
	defer signal.Stop(signalCh)
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	for {
		select {
		case err := <-serverErr:
			if err == http.ErrServerClosed {
				return nil
			}
			return err
		case <-signalCh:
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			return server.Shutdown(ctx)
		case now := <-ticker.C:
			if a.expired(now, cfg.idleTimeout, cfg.startupTimeout) {
				log.Print("Desktop closed after heartbeat timeout")
				ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
				defer cancel()
				return server.Shutdown(ctx)
			}
		}
	}
}

func defaultDataDir(base string) string {
	current := filepath.Join(base, "NTKSoundLabStudio")
	previous := filepath.Join(base, "NTKOmniStreamStudio")
	// Keep opening the earlier profile in place on upgraded installations.
	for _, name := range []string{"profile", "models"} {
		for _, candidate := range []string{current, previous} {
			if info, err := os.Stat(filepath.Join(candidate, name)); err == nil && info.IsDir() {
				return candidate
			}
		}
	}
	return current
}

func main() {
	base := os.Getenv("LOCALAPPDATA")
	if base == "" {
		base, _ = os.UserConfigDir()
	}
	var cfg config
	flag.IntVar(&cfg.port, "port", defaultPort, "Stable loopback port; changing it selects different browser storage")
	flag.StringVar(&cfg.dataDir, "data-dir", defaultDataDir(base), "Durable app data directory (use a separate directory for tests)")
	flag.BoolVar(&cfg.headless, "headless", false, "Start only the loopback service; do not open a browser or existing profile")
	flag.DurationVar(&cfg.idleTimeout, "idle-timeout", 90*time.Second, "Exit after this interval without a heartbeat")
	flag.DurationVar(&cfg.startupTimeout, "startup-timeout", 90*time.Second, "Exit if no UI connects within this interval")
	flag.Parse()
	if err := run(cfg); err != nil {
		log.Printf("Desktop could not start: %v", err)
		if !cfg.headless {
			showStartupError(err.Error())
		}
		os.Exit(1)
	}
}
