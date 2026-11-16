<?php

use App\Http\Controllers\SoundLabController;
use App\Http\Controllers\SunoProxyController;
use Illuminate\Support\Facades\Route;

// Main Studio Interface
Route::get('/', function () {
    return view('welcome');
});

// Direct support for PWA app shell and legacy bookmarks hitting /index.html
Route::get('/index.html', function () {
    return view('welcome');
});

// Global CORS Preflight handling for API routes
Route::options('/api/{any}', function () {
    return response('', 204, [
        'Access-Control-Allow-Origin' => '*',
        'Access-Control-Allow-Methods' => 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers' => 'Content-Type, Authorization, X-Requested-With, X-Admin-Key',
    ]);
})->where('any', '.*');

// Proxy API Routes (Directly callable by client-side browser) with rate limiting
Route::prefix('api')->middleware(['throttle:60,1'])->group(function () {
    // Health & Capabilities
    Route::get('/health', [SoundLabController::class, 'capabilities']);
    Route::get('/capabilities', [SoundLabController::class, 'capabilities']);

    // Universal Media Extractor
    Route::get('/omni/resolve', [SoundLabController::class, 'resolve']);
    Route::get('/omni/direct-stream', [SoundLabController::class, 'directStream']);
    Route::get('/omni/passthrough', [SoundLabController::class, 'passthrough']);
    Route::post('/omni/download', [SoundLabController::class, 'download'])->middleware('throttle:10,1');
    Route::get('/omni/status/{id}', [SoundLabController::class, 'status']);
    Route::get('/omni/stream/{id}', [SoundLabController::class, 'stream']);
    Route::get('/omni/cookies', [SoundLabController::class, 'getCookies']);
    Route::post('/omni/cookies', [SoundLabController::class, 'saveCookies']);
    Route::get('/omni/storage-stats', [SoundLabController::class, 'storageStats']);
    Route::get('/storage/stats', [SoundLabController::class, 'storageStats']);

    // Stems Engine Status
    Route::get('/stems/capabilities', [SoundLabController::class, 'stemCapabilities']);

    // Suno AI Mango DRM, Audio Streaming & Metadata Proxy
    Route::post('/mango/rights', [SunoProxyController::class, 'mangoRights']);
    Route::get('/suno/unshorten', [SunoProxyController::class, 'unshorten']);
    Route::get('/suno/stream/{id}', [SunoProxyController::class, 'streamAudio']);
    Route::get('/suno/song/{id}', [SunoProxyController::class, 'clipMetadata']);
    Route::get('/suno/clip/{id}', [SunoProxyController::class, 'clipMetadata']);
    Route::get('/suno/playlist/{id}', [SunoProxyController::class, 'playlistMetadata']);

    // Public AI & Creator Audio Proxies (ACE Music, Flow Music, Treblo, Audius, Vocaroo)
    Route::get('/acemusic/stream/{id}', [SoundLabController::class, 'aceMusicStream']);
    Route::get('/acemusic/cover/{id}', [SoundLabController::class, 'aceMusicCover']);
    Route::get('/{provider}/stream/{id}', [SoundLabController::class, 'ogProviderStream'])
        ->where('provider', 'flowmusic|treblo');
    Route::get('/{provider}/cover/{id}', [SoundLabController::class, 'ogProviderCover'])
        ->where('provider', 'flowmusic|treblo');
    Route::get('/audius/stream/{id}', [SoundLabController::class, 'audiusStream']);
    Route::get('/audius/cover/{id}', [SoundLabController::class, 'audiusCover']);
    Route::get('/vocaroo/stream/{id}', [SoundLabController::class, 'vocarooStream']);
});
