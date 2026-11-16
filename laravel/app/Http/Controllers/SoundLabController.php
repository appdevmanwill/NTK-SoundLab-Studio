<?php

namespace App\Http\Controllers;

use App\Http\Responses\LockedBinaryFileResponse;
use App\Models\MediaDownload;
use App\Services\UniversalMediaService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\File;
use Symfony\Component\HttpFoundation\BinaryFileResponse;
use Symfony\Component\HttpFoundation\StreamedResponse;
use Symfony\Component\HttpKernel\Exception\HttpExceptionInterface;

class SoundLabController extends Controller
{
    protected UniversalMediaService $mediaService;

    public function __construct(UniversalMediaService $mediaService)
    {
        $this->mediaService = $mediaService;
    }

    /**
     * GET /api/capabilities or /api/health
     */
    public function capabilities(): JsonResponse
    {
        return response()->json(
            $this->mediaService->getCapabilities(),
            200,
            ['Access-Control-Allow-Origin' => '*']
        );
    }

    /**
     * GET /api/omni/resolve?url=<url>
     */
    public function resolve(Request $request): JsonResponse
    {
        $url = $request->query('url');
        if (! is_string($url) || trim($url) === '') {
            return response()->json(['error' => "Missing 'url' query parameter."], 400);
        }

        try {
            $metadata = $this->mediaService->resolveMetadata($url);

            return response()->json($metadata, 200, ['Access-Control-Allow-Origin' => '*']);
        } catch (\Throwable $e) {
            return $this->mediaError($e);
        }
    }

    /**
     * POST /api/omni/download
     * Payload: { url: string, format?: string, is_audio_only?: boolean }
     */
    public function download(Request $request): JsonResponse
    {
        $url = $request->input('url');
        if (! is_string($url) || trim($url) === '') {
            return response()->json(['error' => "Missing 'url' parameter."], 400);
        }

        $format = $request->input('format', 'mp3');
        if (! is_string($format)) {
            return response()->json(['error' => 'Invalid output format.'], 422);
        }
        $isAudioOnly = filter_var($request->input('is_audio_only', $request->input('audioOnly', true)), FILTER_VALIDATE_BOOLEAN);

        try {
            $job = $this->mediaService->startDownload($url, $format, $isAudioOnly);

            return response()->json([
                'success' => true,
                'job_id' => $job->id,
                'status' => $job->status,
                'progress' => $job->progress,
                'download_url' => $job->status === 'completed' ? url("/api/omni/stream/{$job->id}") : null,
            ], 200, ['Access-Control-Allow-Origin' => '*']);
        } catch (\Throwable $e) {
            return $this->mediaError($e);
        }
    }

    /**
     * GET /api/omni/passthrough?url=<url>&format=<format>&audio_only=<bool>
     * Zero-Disk Passthrough: Streams media chunks straight to client with 0 bytes written to disk.
     */
    public function passthrough(Request $request): StreamedResponse|JsonResponse
    {
        $url = $request->query('url');
        if (! is_string($url) || trim($url) === '') {
            return response()->json(['error' => "Missing 'url' query parameter."], 400);
        }

        $format = $request->query('format', 'mp3');
        $isAudioOnly = filter_var($request->query('audio_only', true), FILTER_VALIDATE_BOOLEAN);

        try {
            return $this->mediaService->streamPassthrough($url, $format, $isAudioOnly);
        } catch (\Throwable $e) {
            return $this->mediaError($e);
        }
    }

    /**
     * GET /api/omni/status/{id}
     */
    public function status(string $id): JsonResponse
    {
        $job = MediaDownload::find($id);
        if (! $job) {
            return response()->json(['error' => 'Job not found.'], 404);
        }

        return response()->json([
            'job_id' => $job->id,
            'status' => $job->status,
            'progress' => $job->progress,
            'download_url' => $job->status === 'completed' ? url("/api/omni/stream/{$job->id}") : null,
            'error' => $job->error,
        ], 200, ['Access-Control-Allow-Origin' => '*']);
    }

    /**
     * GET /api/omni/stream/{id}
     * Supports HTTP 206 Partial Content byte ranges for smooth audio/video seeking.
     */
    public function stream(string $id): BinaryFileResponse|JsonResponse
    {
        $lock = fopen(storage_path('app/downloads.lock'), 'c');
        if (! $lock || ! flock($lock, LOCK_SH | LOCK_NB)) {
            if ($lock) {
                fclose($lock);
            }

            return response()->json(['error' => 'Media storage is busy. Please retry.'], 503);
        }
        $job = MediaDownload::find($id);
        if (! $job || $job->status !== 'completed' || empty($job->file_path) || ! $this->mediaService->containedDownloadPath($job->file_path) || ($job->expires_at && $job->expires_at->isPast())) {
            flock($lock, LOCK_UN);
            fclose($lock);

            return response()->json(['error' => 'Stream file not found or expired.'], 404);
        }

        $filePath = $job->file_path;
        $mime = File::mimeType($filePath) ?: 'application/octet-stream';
        $filename = basename($filePath);

        $response = new LockedBinaryFileResponse($filePath, $lock, [
            'Content-Type' => $mime,
            'Accept-Ranges' => 'bytes',
            'Access-Control-Allow-Origin' => '*',
            'Content-Disposition' => 'inline; filename="'.$filename.'"',
        ]);

        $response->setAutoEtag();

        return $response;
    }

    /**
     * POST /api/omni/cookies
     */
    public function saveCookies(Request $request): JsonResponse
    {
        if (! $this->adminAuthorized($request)) {
            return response()->json(['error' => 'Cookie management requires a configured server administrator key.'], 403);
        }

        $cookies = $request->input('cookies', '');
        if (! is_string($cookies) || strlen($cookies) > 65536) {
            return response()->json(['error' => 'Cookie file payload exceeds maximum allowed size (64 KB).'], 422);
        }

        try {
            $saved = $this->mediaService->saveCookies($cookies);
        } catch (\InvalidArgumentException $error) {
            return response()->json(['error' => $error->getMessage()], 422);
        }

        return response()->json([
            'success' => $saved,
            'message' => $saved ? 'Cookies saved into server storage.' : 'Could not save cookies.',
        ], $saved ? 200 : 500);
    }

    /**
     * GET /api/omni/cookies
     */
    public function getCookies(Request $request): JsonResponse
    {
        if (! $this->adminAuthorized($request)) {
            return response()->json(['error' => 'Cookie management requires a configured server administrator key.'], 403);
        }

        $cookieContent = $this->mediaService->getCookies();
        $hasCookies = ! empty(trim($cookieContent));

        return response()->json([
            'configured' => $hasCookies,
            'bytes' => strlen($cookieContent),
        ], 200);
    }

    /**
     * GET /api/acemusic/stream/{id}
     */
    public function aceMusicStream(Request $request, string $id): StreamedResponse|JsonResponse
    {
        return $this->ogProviderStream($request, 'acemusic', $id);
    }

    /**
     * GET /api/acemusic/cover/{id}
     */
    public function aceMusicCover(Request $request, string $id): StreamedResponse|JsonResponse
    {
        return $this->ogProviderCover($request, 'acemusic', $id);
    }

    /**
     * GET /api/{provider}/stream/{id}
     */
    public function ogProviderStream(Request $request, string $provider, string $id): StreamedResponse|JsonResponse
    {
        $clean = preg_replace('/\.(mp3|m4a|wav|ogg|opus|aac|flac|webm)$/i', '', $id);
        if (! preg_match('/^[a-zA-Z0-9_-]{4,64}$/', $clean)) {
            return response()->json(['error' => 'A valid song ID is required.'], 422);
        }

        return $this->streamTempBufferedMedia($request, fn (?string $range, string $tmp) => $this->mediaService->fetchOgProviderMedia($provider, $clean, 'audio', $range, $tmp));
    }

    /**
     * GET /api/{provider}/cover/{id}
     */
    public function ogProviderCover(Request $request, string $provider, string $id): StreamedResponse|JsonResponse
    {
        $clean = preg_replace('/\.(jpg|jpeg|png|webp)$/i', '', $id);
        if (! preg_match('/^[a-zA-Z0-9_-]{4,64}$/', $clean)) {
            return response()->json(['error' => 'A valid song ID is required.'], 422);
        }

        return $this->streamTempBufferedMedia($request, fn (?string $range, string $tmp) => $this->mediaService->fetchOgProviderMedia($provider, $clean, 'cover', $range, $tmp));
    }

    /**
     * GET /api/audius/stream/{id}
     */
    public function audiusStream(Request $request, string $id): StreamedResponse|JsonResponse
    {
        $clean = preg_replace('/\.(mp3|m4a)$/i', '', $id);

        return $this->streamTempBufferedMedia($request, fn (?string $range, string $tmp) => $this->mediaService->fetchAudiusMedia($clean, 'audio', $range, $tmp));
    }

    /**
     * GET /api/audius/cover/{id}
     */
    public function audiusCover(Request $request, string $id): StreamedResponse|JsonResponse
    {
        $clean = preg_replace('/\.(jpg|jpeg|png|webp)$/i', '', $id);

        return $this->streamTempBufferedMedia($request, fn (?string $range, string $tmp) => $this->mediaService->fetchAudiusMedia($clean, 'cover', $range, $tmp));
    }

    /**
     * GET /api/vocaroo/stream/{id}
     */
    public function vocarooStream(Request $request, string $id): StreamedResponse|JsonResponse
    {
        $clean = preg_replace('/\.(mp3|ogg)$/i', '', $id);

        return $this->streamTempBufferedMedia($request, fn (?string $range, string $tmp) => $this->mediaService->fetchVocarooMedia($clean, $range, $tmp));
    }

    /**
     * GET /api/omni/direct-stream?url=<url>
     */
    public function directStream(Request $request): StreamedResponse|JsonResponse
    {
        $url = $request->query('url');
        if (! is_string($url) || trim($url) === '') {
            return response()->json(['error' => "Missing 'url' query parameter."], 400);
        }

        return $this->streamTempBufferedMedia($request, fn (?string $range, string $tmp) => $this->mediaService->fetchDirectMedia($url, $range, $tmp));
    }

    /** @param callable(?string, string): array{status: int, headers: array<string, string>, content_type: string} $fetcher */
    protected function streamTempBufferedMedia(Request $request, callable $fetcher): StreamedResponse|JsonResponse
    {
        $range = $request->header('Range');
        if ($range && ! preg_match('/^bytes=(?:[0-9]+-[0-9]*|-[0-9]+)$/', $range)) {
            return response()->json(['error' => 'Only one valid byte range is supported.'], 416);
        }
        $dir = storage_path('app/acemusic-streams');
        File::ensureDirectoryExists($dir, 0700);
        $lock = fopen(storage_path('app/acemusic-streams.lock'), 'c');
        if (! $lock || ! flock($lock, LOCK_EX | LOCK_NB)) {
            if ($lock) {
                fclose($lock);
            }

            return response()->json(['error' => 'Another audio transfer is active. Please retry shortly.'], 429);
        }
        $release = static function () use (&$lock): void {
            if (is_resource($lock)) {
                flock($lock, LOCK_UN);
                fclose($lock);
            }
            $lock = null;
        };
        $temporary = tempnam($dir, 'media-');
        if ($temporary === false) {
            $release();

            return response()->json(['error' => 'Temporary stream storage is unavailable.'], 503);
        }
        register_shutdown_function(static function () use ($temporary, $release): void {
            if (is_file($temporary)) {
                @unlink($temporary);
            }
            $release();
        });
        try {
            $result = $fetcher($range ?: null, $temporary);
            $headers = [
                'Access-Control-Allow-Origin' => '*',
                'Content-Type' => $result['content_type'],
                'Cache-Control' => 'no-store',
                'Accept-Ranges' => 'bytes',
                'Content-Length' => (string) filesize($temporary),
            ];
            if (isset($result['headers']['content-range'])) {
                $headers['Content-Range'] = $result['headers']['content-range'];
            }

            return response()->stream(static function () use ($temporary, $release): void {
                $file = fopen($temporary, 'rb');
                try {
                    if ($file) {
                        while (! feof($file) && ! connection_aborted()) {
                            echo fread($file, 65536);
                        }
                    }
                } finally {
                    if ($file) {
                        fclose($file);
                    }
                    @unlink($temporary);
                    $release();
                }
            }, $result['status'], $headers);
        } catch (\Throwable $e) {
            @unlink($temporary);
            $release();

            return $this->mediaError($e);
        }
    }

    /**
     * GET /api/omni/storage-stats
     */
    public function storageStats(): JsonResponse
    {
        $caps = $this->mediaService->getCapabilities();

        return response()->json($caps['storage'], 200, ['Access-Control-Allow-Origin' => '*']);
    }

    /**
     * GET /api/stems/capabilities
     */
    public function stemCapabilities(): JsonResponse
    {
        return response()->json([
            'available' => false,
            'engine' => 'In-Browser WebGPU/ONNX & Local Helper',
            'device' => 'client',
            'stems' => ['vocals', 'drums', 'bass', 'other', 'instrumental'],
            'supports_vocal_split' => false,
            'note' => 'This server does not run neural separation. The browser engine requires its runtime and model.',
        ], 200, ['Access-Control-Allow-Origin' => '*']);
    }

    protected function adminAuthorized(Request $request): bool
    {
        $key = config('media.admin_key');
        $provided = $request->header('X-Admin-Key');

        return is_string($key) && $key !== '' && is_string($provided) && hash_equals($key, $provided);
    }

    protected function mediaError(\Throwable $error): JsonResponse
    {
        if ($error instanceof \InvalidArgumentException) {
            return response()->json(['error' => $error->getMessage()], 422);
        }
        if ($error instanceof HttpExceptionInterface) {
            return response()->json(['error' => $error->getMessage()], $error->getStatusCode());
        }

        return response()->json(['error' => 'Media processing failed. Please retry or import a local file.'], 502);
    }
}
