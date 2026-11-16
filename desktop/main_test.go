package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"testing/fstest"
	"time"
)

func TestSoundLabDataDirKeepsExistingProfile(t *testing.T) {
	base := t.TempDir()
	current := filepath.Join(base, "NTKSoundLabStudio")
	previous := filepath.Join(base, "NTKOmniStreamStudio")
	if got := defaultDataDir(base); got != current {
		t.Fatalf("fresh default: got %q, want %q", got, current)
	}
	for _, path := range []string{filepath.Join(current, "android-signing"), filepath.Join(current, "models"), filepath.Join(previous, "profile")} {
		if err := os.MkdirAll(path, 0700); err != nil {
			t.Fatal(err)
		}
	}
	if got := defaultDataDir(base); got != previous {
		t.Fatalf("upgrade default: got %q, want %q", got, previous)
	}
	if err := os.Mkdir(filepath.Join(current, "profile"), 0700); err != nil {
		t.Fatal(err)
	}
	if got := defaultDataDir(base); got != current {
		t.Fatalf("existing SoundLab default: got %q, want %q", got, current)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }
func testApp() *desktopApp {
	return &desktopApp{assets: fstest.MapFS{"index.html": {Data: []byte("fixture")}, "js/app.js": {Data: []byte("export const ok=true;")}}, client: &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		return nil, errors.New("external network disabled in tests")
	})}, host: "127.0.0.1:47831", token: "test-session", started: time.Now(), lastHeartbeat: time.Now()}
}
func serve(a *desktopApp, m, p, b string, authorized bool) *httptest.ResponseRecorder {
	r := httptest.NewRequest(m, "http://"+a.host+p, strings.NewReader(b))
	if authorized {
		r.AddCookie(&http.Cookie{Name: sessionCookie, Value: a.token})
	}
	w := httptest.NewRecorder()
	a.routes().ServeHTTP(w, r)
	return w
}

func TestSessionAndOriginGuards(t *testing.T) {
	a := testApp()
	if w := serve(a, "GET", "/api/capabilities", "", false); w.Code != 401 {
		t.Fatalf("missing session: %d", w.Code)
	}
	if w := serve(a, "GET", "/", "", false); w.Code != 200 || !strings.Contains(w.Header().Get("Set-Cookie"), "HttpOnly") {
		t.Fatal("entry did not establish protected session")
	}
	for _, tc := range []struct{ host, origin, site string }{{"evil.example:47831", "", ""}, {a.host, "https://evil.example", ""}, {a.host, "", "cross-site"}, {a.host, "", "same-site"}} {
		r := httptest.NewRequest("POST", "http://"+a.host+"/api/desktop/heartbeat", nil)
		r.Host = tc.host
		r.Header.Set("Origin", tc.origin)
		r.Header.Set("Sec-Fetch-Site", tc.site)
		r.AddCookie(&http.Cookie{Name: sessionCookie, Value: a.token})
		w := httptest.NewRecorder()
		a.routes().ServeHTTP(w, r)
		if w.Code != 403 {
			t.Errorf("guard accepted %+v: %d", tc, w.Code)
		}
	}
	if w := serve(a, "POST", "/api/desktop/heartbeat", "", true); w.Code != 204 {
		t.Fatalf("same-origin heartbeat failed: %d", w.Code)
	}
	if w := serve(a, "GET", "/api/desktop/shutdown", "", true); w.Code != 404 {
		t.Fatal("shutdown endpoint must not exist")
	}
}

func TestMethodErrorsAndMissingAssets(t *testing.T) {
	a := testApp()
	for _, tc := range []struct {
		method, path string
		status       int
	}{{"GET", "/api/desktop/heartbeat", 405}, {"POST", "/js/app.js", 405}, {"GET", "/missing.js", 404}, {"GET", "/api/unknown", 404}, {"GET", "/models/../secret.txt", 400}, {"GET", "/models/other.onnx", 404}, {"GET", "/models/..%5csecret.txt", 400}} {
		w := serve(a, tc.method, tc.path, "", true)
		if w.Code != tc.status {
			t.Errorf("%s %s: got %d want %d", tc.method, tc.path, w.Code, tc.status)
		}
	}
}

func TestTruthfulUnsupportedJobs(t *testing.T) {
	a := testApp()
	w := serve(a, "POST", "/api/omni/download", `{"url":"https://www.youtube.com/watch?v=x","format":"mp3"}`, true)
	if w.Code != 501 || strings.Contains(w.Body.String(), "job_id") {
		t.Fatalf("invented job: %d %s", w.Code, w.Body.String())
	}
	if w := serve(a, "GET", "/api/omni/status/fabricated", "", true); w.Code != 404 {
		t.Fatal("unknown job was accepted")
	}
	if w := serve(a, "GET", "/api/capabilities", "", true); !strings.Contains(w.Body.String(), `"available":false`) || !strings.Contains(w.Body.String(), `"download_jobs":false`) {
		t.Fatal("capabilities claim absent engines")
	}
}

func TestBoundedBodiesAndIDs(t *testing.T) {
	a := testApp()
	for _, body := range []string{`{"uuid":"bad"}`, `{} {}`, `{"uuid":"` + strings.Repeat("x", maxJSON) + `"}`} {
		if w := serve(a, "POST", "/api/mango/rights", body, true); w.Code != 400 {
			t.Errorf("invalid body got %d", w.Code)
		}
	}
	for _, p := range []string{"/api/clip/prefix-12345678-1234-1234-1234-123456789abc", "/api/playlist/not-a-uuid", "/api/suno/stream/https:evil"} {
		if w := serve(a, "GET", p, "", true); w.Code != 400 {
			t.Errorf("invalid ID got %d", w.Code)
		}
	}
}

func TestURLAndIPPolicy(t *testing.T) {
	for _, raw := range []string{"file:///C:/secret.mp3", "http://localhost/a.mp3", "http://127.0.0.1/a.mp3", "http://192.168.0.1/a.mp3", "https://public.example:8443/a", "https://name:password@public.example/a", "http://[::1]/a", "http://public.example\\@127.0.0.1/a"} {
		if _, err := validateURL(raw); err == nil {
			t.Errorf("accepted %s", raw)
		}
	}
	for _, raw := range []string{"https://cdn.suno.ai/a.mp3", "https://example.com:443/a.mp3?x=1", "http://example.com/a.mp3"} {
		if _, err := validateURL(raw); err != nil {
			t.Errorf("rejected public URL %s: %v", raw, err)
		}
	}
	for _, ip := range []string{"127.0.0.1", "10.1.2.3", "192.168.1.2", "169.254.169.254", "100.64.0.1", "::1", "::ffff:127.0.0.1", "2001:db8::1", "64:ff9b::7f00:1"} {
		if publicIP(netip.MustParseAddr(ip)) {
			t.Errorf("accepted restricted %s", ip)
		}
	}
	if !publicIP(netip.MustParseAddr("8.8.8.8")) {
		t.Fatal("rejected public IPv4")
	}
}

func TestDNSMixedAndRebindingTargetsBlocked(t *testing.T) {
	for _, ips := range [][]net.IPAddr{{{IP: net.ParseIP("127.0.0.1")}}, {{IP: net.ParseIP("8.8.8.8")}, {IP: net.ParseIP("10.0.0.1")}}} {
		dial := publicDialer(func(context.Context, string) ([]net.IPAddr, error) { return ips, nil })
		if _, err := dial(context.Background(), "tcp", "example.com:443"); err == nil || !strings.Contains(err.Error(), "private") {
			t.Fatal("private DNS target was not blocked before dial")
		}
	}
	c := safeClient()
	u, _ := url.Parse("http://127.0.0.1/private")
	if err := c.CheckRedirect(&http.Request{URL: u}, nil); err == nil {
		t.Fatal("private redirect accepted")
	}
}

func TestShortlinkScopeAndRedirect(t *testing.T) {
	a := testApp()
	calls := 0
	a.client = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		return &http.Response{StatusCode: 302, Header: http.Header{"Location": []string{"http://127.0.0.1/private"}}, Body: io.NopCloser(strings.NewReader("")), Request: r}, nil
	})}
	if _, err := a.resolveSuno(context.Background(), "https://suno.com/s/abc"); err == nil {
		t.Fatal("unsafe redirect accepted")
	}
	if calls != 1 {
		t.Fatalf("redirect was fetched: %d requests", calls)
	}
	calls = 0
	if _, err := a.resolveSuno(context.Background(), "https://attacker.example/s/a"); err == nil || calls != 0 {
		t.Fatal("non-Suno shortlink was requested")
	}
}

func TestHeartbeatReloadLifecycle(t *testing.T) {
	a := testApp()
	now := time.Now()
	a.started = now.Add(-100 * time.Second)
	if !a.expired(now, 90*time.Second, 90*time.Second) {
		t.Fatal("failed browser startup leaked server")
	}
	a.touch()
	if a.expired(time.Now().Add(4*time.Second), 90*time.Second, 90*time.Second) {
		t.Fatal("reload grace prematurely expires")
	}
	if !a.expired(time.Now().Add(91*time.Second), 90*time.Second, 90*time.Second) {
		t.Fatal("closed browser did not expire")
	}
}

func TestProxySizeAndRange(t *testing.T) {
	a := testApp()
	id := "12345678-1234-1234-1234-123456789abc"
	a.client = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if strings.Contains(r.URL.Path, "/clip/") && strings.HasSuffix(r.URL.Path, ".m4a") {
			if r.Header.Get("Range") != "bytes=10-19" {
				t.Error("range not forwarded")
			}
			return &http.Response{StatusCode: 206, Header: http.Header{"Content-Type": []string{"audio/mp4"}, "Content-Range": []string{"bytes 10-19/100"}}, Body: io.NopCloser(strings.NewReader("0123456789")), ContentLength: 10, Request: r}, nil
		}
		return &http.Response{StatusCode: 200, Header: http.Header{}, Body: io.NopCloser(strings.NewReader(`{"x":"` + strings.Repeat("a", maxJSON) + `"}`)), Request: r}, nil
	})}
	if w := serve(a, "GET", "/api/clip/"+id, "", true); w.Code != 502 {
		t.Fatal("oversized provider body accepted")
	}
	r := httptest.NewRequest("GET", "http://"+a.host+"/api/suno/stream/"+id, nil)
	r.AddCookie(&http.Cookie{Name: sessionCookie, Value: a.token})
	r.Header.Set("Range", "bytes=10-19")
	w := httptest.NewRecorder()
	a.routes().ServeHTTP(w, r)
	if w.Code != 206 || w.Body.String() != "0123456789" || w.Header().Get("Content-Range") != "bytes 10-19/100" {
		t.Fatalf("range forwarding failed: %d %s", w.Code, w.Body.String())
	}
}

func TestProviderStreamRejectsHTMLAndUntrustedRedirects(t *testing.T) {
	a := testApp()
	a.client.Transport = roundTripFunc(func(r *http.Request) (*http.Response, error) {
		return &http.Response{
			StatusCode: 200,
			Header:     http.Header{"Content-Type": []string{"text/html"}},
			Body:       io.NopCloser(strings.NewReader("<!doctype html><p>fixture</p>")),
			Request:    r,
		}, nil
	})
	w := serve(a, "GET", "/api/suno/stream/12345678-1234-1234-1234-123456789abc", "", true)
	if w.Code != 502 || strings.Contains(w.Body.String(), "<!doctype") {
		t.Fatalf("provider HTML passed through: %d %s", w.Code, w.Body.String())
	}

	client := providerClient(safeClient(), "provider.example")
	for _, target := range []string{"http://provider.example/audio", "https://unrelated.example/audio"} {
		u, err := url.Parse(target)
		if err != nil {
			t.Fatal(err)
		}
		if client.CheckRedirect(&http.Request{URL: u}, nil) == nil {
			t.Fatalf("accepted unsafe redirect %s", target)
		}
	}

	aceAssetClient := aceMusicClient(safeClient(), true)
	r2URL, _ := url.Parse("https://demo.r2.cloudflarestorage.com/acemusic-data-prod/track.mp3")
	if err := aceAssetClient.CheckRedirect(&http.Request{URL: r2URL}, nil); err != nil {
		t.Fatalf("rejected legitimate ACE Music R2 redirect: %v", err)
	}
	evilURL, _ := url.Parse("https://unrelated.example/track.mp3")
	if err := aceAssetClient.CheckRedirect(&http.Request{URL: evilURL}, nil); err == nil {
		t.Fatal("accepted untrusted ACE Music redirect")
	}
}

func TestAceMusicResolveAndStreams(t *testing.T) {
	a := testApp()
	htmlPage := `<!doctype html><html><head>
		<meta property="og:title" content="Echoes of Tomorrow par SynthWave Lab | ACE Music">
		<meta name="description" content="Synthwave dreamscape">
		<meta property="og:audio" content="/data/so_demo123.mp3">
		<meta property="og:image" content="/data/co_demo123.jpg">
	</head><body></body></html>`
	returnHTMLOnAudio := false
	returnHTMLOnCover := false
	a.client = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		switch r.URL.String() {
		case "https://acemusic.ai/song/d3wxbtudvpih":
			return &http.Response{
				StatusCode: 200,
				Header:     http.Header{"Content-Type": []string{"text/html; charset=utf-8"}},
				Body:       io.NopCloser(strings.NewReader(htmlPage)),
				Request:    r,
			}, nil
		case "https://acemusic.ai/data/so_demo123.mp3":
			if returnHTMLOnAudio {
				return &http.Response{
					StatusCode: 200,
					Header:     http.Header{"Content-Type": []string{"text/html"}},
					Body:       io.NopCloser(strings.NewReader("<html>not mp3</html>")),
					Request:    r,
				}, nil
			}
			if r.Header.Get("Range") == "bytes=2-5" {
				return &http.Response{
					StatusCode:    206,
					Header:        http.Header{"Content-Type": []string{"audio/mpeg"}, "Content-Range": []string{"bytes 2-5/10"}},
					Body:          io.NopCloser(strings.NewReader("ABCD")),
					ContentLength: 4,
					Request:       r,
				}, nil
			}
			return &http.Response{
				StatusCode:    200,
				Header:        http.Header{"Content-Type": []string{"audio/mpeg"}},
				Body:          io.NopCloser(strings.NewReader("0123456789")),
				ContentLength: 10,
				Request:       r,
			}, nil
		case "https://acemusic.ai/data/co_demo123.jpg":
			if returnHTMLOnCover {
				return &http.Response{
					StatusCode: 200,
					Header:     http.Header{"Content-Type": []string{"text/html"}},
					Body:       io.NopCloser(strings.NewReader("<html>not image</html>")),
					Request:    r,
				}, nil
			}
			return &http.Response{
				StatusCode:    200,
				Header:        http.Header{"Content-Type": []string{"image/jpeg"}},
				Body:          io.NopCloser(strings.NewReader("JPEGBYTES")),
				ContentLength: 9,
				Request:       r,
			}, nil
		default:
			t.Fatalf("unexpected upstream request: %s", r.URL.String())
			return nil, errors.New("unexpected")
		}
	})}

	target := url.QueryEscape("https://acemusic.ai/fr/song/d3wxbtudvpih?sh=hcCYFakWHxi")
	w := serve(a, "GET", "/api/omni/resolve?url="+target, "", true)
	if w.Code != 200 {
		t.Fatalf("ace resolve failed: %d %s", w.Code, w.Body.String())
	}
	var meta map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &meta); err != nil {
		t.Fatal(err)
	}
	if meta["uuid"] != "acemusic-d3wxbtudvpih" || meta["title"] != "Echoes of Tomorrow" || meta["artist"] != "SynthWave Lab" || meta["streamUrl"] != "/api/acemusic/stream/d3wxbtudvpih" || meta["imageLarge"] != "/api/acemusic/cover/d3wxbtudvpih" {
		t.Fatalf("unexpected ace metadata: %+v", meta)
	}

	req := httptest.NewRequest("GET", "http://"+a.host+"/api/acemusic/stream/d3wxbtudvpih", nil)
	req.AddCookie(&http.Cookie{Name: sessionCookie, Value: a.token})
	req.Header.Set("Range", "bytes=2-5")
	rw := httptest.NewRecorder()
	a.routes().ServeHTTP(rw, req)
	if rw.Code != 206 || rw.Body.String() != "ABCD" || rw.Header().Get("Content-Type") != "audio/mpeg" {
		t.Fatalf("ace stream range failed: %d %s", rw.Code, rw.Body.String())
	}

	if cw := serve(a, "GET", "/api/acemusic/cover/d3wxbtudvpih", "", true); cw.Code != 200 || cw.Body.String() != "JPEGBYTES" {
		t.Fatalf("ace cover failed: %d %s", cw.Code, cw.Body.String())
	}

	returnHTMLOnAudio = true
	if badAudio := serve(a, "GET", "/api/acemusic/stream/d3wxbtudvpih", "", true); badAudio.Code != 502 {
		t.Fatalf("expected 502 for HTML audio payload, got %d", badAudio.Code)
	}
	returnHTMLOnAudio = false

	returnHTMLOnCover = true
	if badCover := serve(a, "GET", "/api/acemusic/cover/d3wxbtudvpih", "", true); badCover.Code != 502 {
		t.Fatalf("expected 502 for HTML cover payload, got %d", badCover.Code)
	}
}

func TestDirectMediaProxyAndAudiomackTruth(t *testing.T) {
	a := testApp()
	calls := 0
	returnHTML := false
	a.client = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		if r.URL.String() != "https://cdn.example/audio/track.mp3" {
			t.Fatalf("unexpected direct fetch: %s", r.URL.String())
		}
		if r.Method == "HEAD" {
			return &http.Response{StatusCode: http.StatusMethodNotAllowed, Header: http.Header{}, Body: io.NopCloser(strings.NewReader("")), Request: r}, nil
		}
		if returnHTML {
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"text/html"}}, Body: io.NopCloser(strings.NewReader("<html>bad</html>")), Request: r}, nil
		}
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/mpeg"}}, Body: io.NopCloser(strings.NewReader("MP3DATA")), ContentLength: 7, Request: r}, nil
	})}

	amURL := url.QueryEscape("https://audiomack.com/artist/song/track")
	w := serve(a, "GET", "/api/omni/resolve?url="+amURL, "", true)
	if w.Code != 422 || !strings.Contains(w.Body.String(), "OAuth") || !strings.Contains(w.Body.String(), "Media Grabber") || calls != 0 {
		t.Fatalf("unexpected audiomack response (%d, calls=%d): %s", w.Code, calls, w.Body.String())
	}

	directURL := url.QueryEscape("https://cdn.example/audio/track.mp3")
	dw := serve(a, "GET", "/api/omni/resolve?url="+directURL, "", true)
	if dw.Code != 200 {
		t.Fatalf("direct resolve failed after 405 HEAD fallback: %d %s", dw.Code, dw.Body.String())
	}
	var meta map[string]any
	if err := json.Unmarshal(dw.Body.Bytes(), &meta); err != nil {
		t.Fatal(err)
	}
	streamPath, _ := meta["streamUrl"].(string)
	if !strings.HasPrefix(streamPath, "/api/omni/direct-stream?url=") {
		t.Fatalf("expected proxied direct-stream URL, got %q", streamPath)
	}

	sw := serve(a, "GET", streamPath, "", true)
	if sw.Code != 200 || sw.Body.String() != "MP3DATA" {
		t.Fatalf("direct-stream failed: %d %s", sw.Code, sw.Body.String())
	}

	returnHTML = true
	if bw := serve(a, "GET", streamPath, "", true); bw.Code != 502 {
		t.Fatalf("expected 502 when direct stream returns HTML, got %d", bw.Code)
	}

	if rw := serve(a, "GET", "/api/omni/direct-stream?url="+url.QueryEscape("https://cdn.example/page.html"), "", true); rw.Code != 422 {
		t.Fatalf("expected 422 for non-media extension, got %d", rw.Code)
	}
}

func TestFlowTrebloAudiusVocarooAndDRMTruth(t *testing.T) {
	a := testApp()
	a.client = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		switch r.URL.String() {
		case "https://www.flowmusic.app/song/00032777-30b1-482a-8e3f-d3fd44169009":
			page := `<html><head><meta property="og:title" content="Sunset Flow by Maker | Flow Music"/><meta property="og:audio" content="https://storage.googleapis.com/producer-app-public/clips/00032777-30b1-482a-8e3f-d3fd44169009.m4a"/><meta property="og:image" content="https://storage.googleapis.com/producer-app-public/assets/art.jpg"/></head></html>`
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"text/html"}}, Body: io.NopCloser(strings.NewReader(page)), Request: r}, nil
		case "https://storage.googleapis.com/producer-app-public/clips/00032777-30b1-482a-8e3f-d3fd44169009.m4a":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/mp4"}}, Body: io.NopCloser(strings.NewReader("FLOWM4A")), ContentLength: 7, Request: r}, nil
		case "https://treblo.com/song/1b794faa-ad4f-483a-af70-93de2322937a":
			page := `<html><head><meta property="og:title" content="Night Drive"/><meta property="og:audio" content="https://cdn.treblo.com/generations3/audio_1.ogg"/></head></html>`
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"text/html"}}, Body: io.NopCloser(strings.NewReader(page)), Request: r}, nil
		case "https://cdn.treblo.com/generations3/audio_1.ogg":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/ogg"}}, Body: io.NopCloser(strings.NewReader("OggS123")), ContentLength: 7, Request: r}, nil
		case "https://api.audius.co/v1/resolve?url=https%3A%2F%2Faudius.co%2Fcamouflybeats%2Fhypermantra-86216":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"data":{"id":"V4W8r","title":"HYPERMANTRA","duration":180,"genre":"Electronic","user":{"name":"camoufly"},"artwork":{"480x480":"https://node.audius.co/art.jpg","mirrors":["https://cn1.mainnet.audiusindex.org"]}}}`)), Request: r}, nil
		case "https://api.audius.co/v1/tracks/V4W8r/stream":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/mpeg"}}, Body: io.NopCloser(strings.NewReader("AUDMP3")), ContentLength: 6, Request: r}, nil
		case "https://api.audius.co/v1/tracks/V4W8r":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"data":{"id":"V4W8r","artwork":{"480x480":"https://node.audius.co/art.jpg","mirrors":["https://cn1.mainnet.audiusindex.org"]}}}`)), Request: r}, nil
		case "https://node.audius.co/art.jpg":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"image/jpeg"}}, Body: io.NopCloser(strings.NewReader("AUART")), ContentLength: 5, Request: r}, nil
		case "https://media1.vocaroo.com/mp3/123456789012":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/mpeg"}}, Body: io.NopCloser(strings.NewReader("VOCMP3")), ContentLength: 6, Request: r}, nil
		case "https://cdn.example/signed/track.aac":
			if r.Method == "HEAD" {
				return &http.Response{StatusCode: http.StatusForbidden, Header: http.Header{}, Body: io.NopCloser(strings.NewReader("")), Request: r}, nil
			}
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/aac"}}, Body: io.NopCloser(strings.NewReader("AACDATA")), ContentLength: 7, Request: r}, nil
		default:
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.String())
			return nil, nil
		}
	})}

	wf := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape("https://www.riffusion.com/song/00032777-30b1-482a-8e3f-d3fd44169009"), "", true)
	if wf.Code != 200 || !strings.Contains(wf.Body.String(), "/api/flowmusic/stream/00032777-30b1-482a-8e3f-d3fd44169009") {
		t.Fatalf("flow resolve failed: %d %s", wf.Code, wf.Body.String())
	}
	if sf := serve(a, "GET", "/api/flowmusic/stream/00032777-30b1-482a-8e3f-d3fd44169009", "", true); sf.Code != 200 || sf.Body.String() != "FLOWM4A" {
		t.Fatalf("flow stream failed: %d %s", sf.Code, sf.Body.String())
	}

	wt := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape("https://sonauto.ai/song/1b794faa-ad4f-483a-af70-93de2322937a"), "", true)
	if wt.Code != 200 || !strings.Contains(wt.Body.String(), "/api/treblo/stream/1b794faa-ad4f-483a-af70-93de2322937a") {
		t.Fatalf("treblo resolve failed: %d %s", wt.Code, wt.Body.String())
	}
	if st := serve(a, "GET", "/api/treblo/stream/1b794faa-ad4f-483a-af70-93de2322937a", "", true); st.Code != 200 || st.Body.String() != "OggS123" {
		t.Fatalf("treblo stream failed: %d %s", st.Code, st.Body.String())
	}

	wa := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape("https://audius.co/camouflybeats/hypermantra-86216"), "", true)
	if wa.Code != 200 || !strings.Contains(wa.Body.String(), "/api/audius/stream/V4W8r") {
		t.Fatalf("audius resolve failed: %d %s", wa.Code, wa.Body.String())
	}
	if sa := serve(a, "GET", "/api/audius/stream/V4W8r", "", true); sa.Code != 200 || sa.Body.String() != "AUDMP3" {
		t.Fatalf("audius stream failed: %d %s", sa.Code, sa.Body.String())
	}
	if ca := serve(a, "GET", "/api/audius/cover/V4W8r", "", true); ca.Code != 200 || ca.Body.String() != "AUART" {
		t.Fatalf("audius cover failed: %d %s", ca.Code, ca.Body.String())
	}

	wv := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape("https://voca.ro/123456789012"), "", true)
	if wv.Code != 200 || !strings.Contains(wv.Body.String(), "/api/vocaroo/stream/123456789012") {
		t.Fatalf("vocaroo resolve failed: %d %s", wv.Code, wv.Body.String())
	}
	if sv := serve(a, "GET", "/api/vocaroo/stream/123456789012", "", true); sv.Code != 200 || sv.Body.String() != "VOCMP3" {
		t.Fatalf("vocaroo stream failed: %d %s", sv.Code, sv.Body.String())
	}

	w403 := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape("https://cdn.example/signed/track.aac"), "", true)
	if w403.Code != 200 || !strings.Contains(w403.Body.String(), "/api/omni/direct-stream") {
		t.Fatalf("403 HEAD fallback failed for .aac: %d %s", w403.Code, w403.Body.String())
	}

	if wh := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape("https://cdn.example/live/playlist.m3u8"), "", true); wh.Code != 422 {
		t.Fatalf("expected 422 for HLS m3u8 in desktop native mode, got %d", wh.Code)
	}
	for _, drmURL := range []string{"https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT", "https://tidal.com/browse/track/1", "https://www.deezer.com/track/1"} {
		if wd := serve(a, "GET", "/api/omni/resolve?url="+url.QueryEscape(drmURL), "", true); wd.Code != 422 || !strings.Contains(wd.Body.String(), "DRM") {
			t.Fatalf("expected 422 DRM message for %s, got %d %s", drmURL, wd.Code, wd.Body.String())
		}
	}
}

func TestGrabbedExtensionlessDirectStreamStrictMime(t *testing.T) {
	a := testApp()
	a.client = &http.Client{Transport: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		switch r.URL.String() {
		case "https://cdn.example/stream/track123":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"audio/mp4"}}, Body: io.NopCloser(strings.NewReader("GRABM4A")), ContentLength: 7, Request: r}, nil
		case "https://cdn.example/stream/rawbin":
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/octet-stream"}}, Body: io.NopCloser(strings.NewReader("RAWBIN")), ContentLength: 6, Request: r}, nil
		default:
			return nil, fmt.Errorf("unexpected URL: %s", r.URL.String())
		}
	})}

	if noGrab := serve(a, "GET", "/api/omni/direct-stream?url="+url.QueryEscape("https://cdn.example/stream/track123"), "", true); noGrab.Code != 422 {
		t.Fatalf("expected 422 without grab=1, got %d", noGrab.Code)
	}
	if okGrab := serve(a, "GET", "/api/omni/direct-stream?url="+url.QueryEscape("https://cdn.example/stream/track123")+"&grab=1", "", true); okGrab.Code != 200 || okGrab.Body.String() != "GRABM4A" {
		t.Fatalf("expected 200 for extension-less grabbed audio/mp4, got %d %s", okGrab.Code, okGrab.Body.String())
	}
	if badOctet := serve(a, "GET", "/api/omni/direct-stream?url="+url.QueryEscape("https://cdn.example/stream/rawbin")+"&grab=1", "", true); badOctet.Code != 502 {
		t.Fatalf("expected 502 for extension-less application/octet-stream, got %d", badOctet.Code)
	}
	if badExt := serve(a, "GET", "/api/omni/direct-stream?url="+url.QueryEscape("https://cdn.example/page.html")+"&grab=1", "", true); badExt.Code != 422 {
		t.Fatalf("expected 422 for .html even with grab=1, got %d", badExt.Code)
	}
}
