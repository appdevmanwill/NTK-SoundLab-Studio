<?php

namespace Tests\Feature;

use App\Services\SafeMediaHttp;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SoundLabApiTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Test capabilities endpoint returns operational status and storage quota info.
     */
    public function test_capabilities_endpoint_returns_status_and_storage(): void
    {
        $response = $this->get('/api/capabilities');

        $response->assertStatus(200);
        $response->assertJsonStructure([
            'status',
            'server',
            'php_version',
            'yt_dlp',
            'ffmpeg',
            'storage' => [
                'downloads_bytes',
                'downloads_formatted',
                'quota_limit_bytes',
                'quota_limit_formatted',
                'quota_used_pct',
                'safe_threshold_ok',
            ],
            'timestamp',
        ]);
        $this->assertEquals('ok', $response->json('status'));
    }

    /**
     * Test health endpoint alias.
     */
    public function test_health_endpoint(): void
    {
        $response = $this->get('/api/health');
        $response->assertStatus(200);
        $this->assertEquals('ok', $response->json('status'));
    }

    /**
     * Test media resolve rejects missing url parameter.
     */
    public function test_resolve_rejects_missing_url(): void
    {
        $response = $this->getJson('/api/omni/resolve');
        $response->assertStatus(400);
        $response->assertJson([
            'error' => "Missing 'url' query parameter.",
        ]);
    }

    /**
     * Test media resolve rejects invalid scheme (e.g. file:// or command flag).
     */
    public function test_resolve_rejects_invalid_url_protocol(): void
    {
        $response = $this->getJson('/api/omni/resolve?url=file:///etc/passwd');
        $response->assertStatus(422);
        $this->assertStringContainsString('HTTP and HTTPS', $response->json('error'));
    }

    /**
     * Test status endpoint returns 404 for unknown job.
     */
    public function test_status_returns_404_for_unknown_job(): void
    {
        $response = $this->getJson('/api/omni/status/non-existent-uuid');
        $response->assertStatus(404);
        $response->assertJson([
            'error' => 'Job not found.',
        ]);
    }

    /**
     * Test Mango Rights proxy rejects invalid or missing UUID.
     */
    public function test_mango_rights_rejects_invalid_uuid(): void
    {
        $response = $this->postJson('/api/mango/rights', [
            'content_params' => [
                'content_id' => 'not-a-valid-uuid',
            ],
        ]);
        $response->assertStatus(422);
        $response->assertJson([
            'error' => 'Invalid or missing Suno song content UUID.',
        ]);
    }

    /**
     * Test storage stats endpoint.
     */
    public function test_storage_stats_endpoint(): void
    {
        $response = $this->getJson('/api/storage/stats');
        $response->assertStatus(200);
        $response->assertJsonStructure([
            'downloads_bytes',
            'downloads_formatted',
            'quota_limit_bytes',
            'quota_limit_formatted',
            'quota_used_pct',
            'safe_threshold_ok',
        ]);
    }

    /**
     * Test Artisan omni:prune command execution.
     */
    public function test_omni_prune_artisan_command(): void
    {
        $this->artisan('omni:prune', ['--max-age' => 30])
            ->assertExitCode(0);
    }

    public function test_resolve_and_stream_acemusic_with_mocked_safe_http(): void
    {
        $html = <<<'HTML'
<!doctype html><html><head>
<meta property="og:title" content="Midnight Signal by PulseForge | ACE Music">
<meta name="description" content="Synth bass">
<meta property="og:audio" content="/data/so_midnight.mp3">
<meta property="og:image" content="/data/co_midnight.jpg">
</head></html>
HTML;

        $fakeHttp = new class extends SafeMediaHttp {
            public function publicAddress(string $url): string
            {
                return '93.184.216.34';
            }

            public function request(string $url, string $method = 'GET', array $headers = [], ?string $body = null, int $maxBytes = 2097152, ?string $destination = null, array $allowedHosts = []): array
            {
                if ($url === 'https://acemusic.ai/song/d3wxbtudvpih') {
                    return ['status' => 200, 'headers' => ['content-type' => 'text/html; charset=utf-8'], 'body' => $GLOBALS['__ace_html'], 'url' => $url];
                }
                if ($url === 'https://acemusic.ai/data/so_midnight.mp3') {
                    file_put_contents($destination, 'ID3MOCKMP3');
                    return ['status' => 200, 'headers' => ['content-type' => 'audio/mpeg'], 'body' => '', 'url' => $url];
                }
                throw new \RuntimeException('Unexpected request: '.$url);
            }
        };
        $GLOBALS['__ace_html'] = $html;
        $this->app->instance(SafeMediaHttp::class, $fakeHttp);

        $resolve = $this->getJson('/api/omni/resolve?url='.urlencode('https://acemusic.ai/song/d3wxbtudvpih?sh=hcCYFakWHxi'));
        $resolve->assertStatus(200)
            ->assertJson([
                'uuid' => 'acemusic-d3wxbtudvpih',
                'title' => 'Midnight Signal',
                'artist' => 'PulseForge',
                'platform' => 'ACE Music',
                'streamUrl' => '/api/acemusic/stream/d3wxbtudvpih',
                'imageLarge' => '/api/acemusic/cover/d3wxbtudvpih',
            ]);

        $stream = $this->get('/api/acemusic/stream/d3wxbtudvpih');
        $stream->assertStatus(200)
            ->assertHeader('Content-Type', 'audio/mpeg');
        $this->assertSame('ID3MOCKMP3', $stream->streamedContent());

        $audiomack = $this->getJson('/api/omni/resolve?url='.urlencode('https://audiomack.com/artist/song/track'));
        $audiomack->assertStatus(422);
        $this->assertStringContainsString('OAuth', $audiomack->json('error'));
    }

    public function test_flowmusic_treblo_audius_vocaroo_direct_and_drm_guardrails(): void
    {
        $fakeHttp = new class extends SafeMediaHttp {
            public function publicAddress(string $url): string
            {
                return '93.184.216.34';
            }

            public function request(string $url, string $method = 'GET', array $headers = [], ?string $body = null, int $maxBytes = 2097152, ?string $destination = null, array $allowedHosts = []): array
            {
                if ($url === 'https://www.flowmusic.app/song/00032777-30b1-482a-8e3f-d3fd44169009') {
                    return [
                        'status' => 200,
                        'headers' => ['content-type' => 'text/html; charset=utf-8'],
                        'body' => '<meta property="og:title" content="Horizon by Maker | Flow Music"><meta property="og:audio" content="https://storage.googleapis.com/producer-app-public/clips/00032777-30b1-482a-8e3f-d3fd44169009.m4a">',
                        'url' => $url,
                    ];
                }
                if ($url === 'https://storage.googleapis.com/producer-app-public/clips/00032777-30b1-482a-8e3f-d3fd44169009.m4a') {
                    file_put_contents($destination, 'FLOWM4A');

                    return ['status' => 200, 'headers' => ['content-type' => 'audio/mp4'], 'body' => '', 'url' => $url];
                }
                if ($url === 'https://treblo.com/song/1b794faa-ad4f-483a-af70-93de2322937a') {
                    return [
                        'status' => 200,
                        'headers' => ['content-type' => 'text/html'],
                        'body' => '<meta property="og:title" content="Sunset Echo"><meta property="og:audio" content="https://cdn.treblo.com/generations3/audio_1.ogg">',
                        'url' => $url,
                    ];
                }
                if ($url === 'https://cdn.treblo.com/generations3/audio_1.ogg') {
                    file_put_contents($destination, 'OGGDATA');

                    return ['status' => 200, 'headers' => ['content-type' => 'audio/ogg'], 'body' => '', 'url' => $url];
                }
                if (str_starts_with($url, 'https://api.audius.co/v1/resolve')) {
                    return [
                        'status' => 200,
                        'headers' => ['content-type' => 'application/json'],
                        'body' => json_encode(['data' => ['id' => 'V4W8r', 'title' => 'HYPERMANTRA', 'duration' => 180, 'genre' => 'Electronic', 'user' => ['name' => 'camoufly'], 'artwork' => ['480x480' => 'https://node.audius.co/art.jpg']]]),
                        'url' => $url,
                    ];
                }
                if ($url === 'https://api.audius.co/v1/tracks/V4W8r/stream') {
                    file_put_contents($destination, 'AUDMP3');

                    return ['status' => 200, 'headers' => ['content-type' => 'audio/mpeg'], 'body' => '', 'url' => $url];
                }
                if ($url === 'https://media1.vocaroo.com/mp3/123456789012') {
                    if ($method === 'HEAD') {
                        return ['status' => 200, 'headers' => ['content-type' => 'audio/mpeg'], 'body' => '', 'url' => $url];
                    }
                    file_put_contents($destination, 'VOCMP3');

                    return ['status' => 200, 'headers' => ['content-type' => 'audio/mpeg'], 'body' => '', 'url' => $url];
                }
                if ($url === 'https://cdn.example.org/audio/sample.aac') {
                    file_put_contents($destination, 'AACDATA');

                    return ['status' => 200, 'headers' => ['content-type' => 'audio/aac'], 'body' => '', 'url' => $url];
                }
                throw new \RuntimeException('Unexpected request: '.$url);
            }
        };
        $this->app->instance(SafeMediaHttp::class, $fakeHttp);

        $flow = $this->getJson('/api/omni/resolve?url='.urlencode('https://www.riffusion.com/song/00032777-30b1-482a-8e3f-d3fd44169009'));
        $flow->assertStatus(200)->assertJson(['platform' => 'Flow Music', 'streamUrl' => '/api/flowmusic/stream/00032777-30b1-482a-8e3f-d3fd44169009']);
        $this->assertSame('FLOWM4A', $this->get('/api/flowmusic/stream/00032777-30b1-482a-8e3f-d3fd44169009')->assertStatus(200)->streamedContent());

        $treblo = $this->getJson('/api/omni/resolve?url='.urlencode('https://sonauto.ai/song/1b794faa-ad4f-483a-af70-93de2322937a'));
        $treblo->assertStatus(200)->assertJson(['platform' => 'Treblo', 'streamUrl' => '/api/treblo/stream/1b794faa-ad4f-483a-af70-93de2322937a']);
        $this->assertSame('OGGDATA', $this->get('/api/treblo/stream/1b794faa-ad4f-483a-af70-93de2322937a')->assertStatus(200)->streamedContent());

        $audius = $this->getJson('/api/omni/resolve?url='.urlencode('https://audius.co/camouflybeats/hypermantra-86216'));
        $audius->assertStatus(200)->assertJson(['platform' => 'Audius', 'streamUrl' => '/api/audius/stream/V4W8r']);
        $this->assertSame('AUDMP3', $this->get('/api/audius/stream/V4W8r')->assertStatus(200)->streamedContent());

        $vocaroo = $this->getJson('/api/omni/resolve?url='.urlencode('https://voca.ro/123456789012'));
        $vocaroo->assertStatus(200)->assertJson(['platform' => 'Vocaroo', 'streamUrl' => '/api/vocaroo/stream/123456789012']);
        $this->assertSame('VOCMP3', $this->get('/api/vocaroo/stream/123456789012')->assertStatus(200)->streamedContent());

        $direct = $this->getJson('/api/omni/resolve?url='.urlencode('https://cdn.example.org/audio/sample.aac'));
        $direct->assertStatus(200)->assertJson(['platform' => 'Direct Media File']);
        $this->assertStringStartsWith('/api/omni/direct-stream?url=', $direct->json('streamUrl'));
        $this->assertSame('AACDATA', $this->get($direct->json('streamUrl'))->assertStatus(200)->streamedContent());

        $this->getJson('/api/omni/resolve?url='.urlencode('https://cdn.example.org/live.m3u8'))->assertStatus(422);
        $this->getJson('/api/omni/resolve?url='.urlencode('https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT'))->assertStatus(422);
    }

    public function test_grabbed_extensionless_direct_stream_enforces_strict_media_mime(): void
    {
        $fakeHttp = new class extends SafeMediaHttp {
            public function publicAddress(string $url): string
            {
                return '93.184.216.34';
            }

            public function request(string $url, string $method = 'GET', array $headers = [], ?string $body = null, int $maxBytes = 2097152, ?string $destination = null, array $allowedHosts = []): array
            {
                if ($url === 'https://cdn.example.org/stream/track123') {
                    file_put_contents($destination, 'GRABM4A');

                    return ['status' => 200, 'headers' => ['content-type' => 'audio/mp4'], 'body' => '', 'url' => $url];
                }
                if ($url === 'https://cdn.example.org/stream/rawbin') {
                    file_put_contents($destination, 'RAWBIN');

                    return ['status' => 200, 'headers' => ['content-type' => 'application/octet-stream'], 'body' => '', 'url' => $url];
                }
                throw new \RuntimeException('Unexpected request: '.$url);
            }
        };
        $this->app->instance(SafeMediaHttp::class, $fakeHttp);

        $this->get('/api/omni/direct-stream?url='.urlencode('https://cdn.example.org/stream/track123'))->assertStatus(422);
        $ok = $this->get('/api/omni/direct-stream?url='.urlencode('https://cdn.example.org/stream/track123').'&grab=1');
        $ok->assertStatus(200);
        $this->assertSame('GRABM4A', $ok->streamedContent());

        $this->get('/api/omni/direct-stream?url='.urlencode('https://cdn.example.org/stream/rawbin').'&grab=1')->assertStatus(502);
        $this->get('/api/omni/direct-stream?url='.urlencode('https://cdn.example.org/page.html').'&grab=1')->assertStatus(422);
    }
}
