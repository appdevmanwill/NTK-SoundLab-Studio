# NTK SoundLab Studio · delivery state

## GitHub publication · 12 November 2026

**VERIFIED · published.** Source commit `87c5a9446b223da255b34658f276233421b1240a` is on `appdevmanwill/NTK-SoundLab-Studio`, tagged `v2026.11.11.2`. The [GitHub preview release](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/tag/v2026.11.11.2) contains eight packages and four supporting files. All 12 attachment sizes and GitHub SHA-256 digests match the local files. The README and setup guides were rewritten for app users and source contributors. New binaries are release attachments, with a flat checksum manifest.

Pre-publication checks passed for the Go desktop core, four helper tests and 24 Laravel tests with 108 assertions. Composer's production lock audit reported no advisories. A source review found no private keys or provider tokens in the staged changes. Physical-device and hosted-service acceptance retain the limits recorded below.

The GitHub release is a preview because phone endurance, graphical Linux installation and actual provider recognition are still open. The previous repository baseline `827b43f` is available for rollback. Publication receipts are under `working/EVIDENCE/github-release-2026-11-12`. Local audit inputs and intermediate release archives were preserved in the workspace.

## Signed Play bundle follow-up · 11 November 2026

- **VERIFIED · AAB.** `SOFTWARE/ANDROID/NTKSoundLab-2026.11.11.2.aab` is signed with the existing SoundLab key. Strict JAR signature verification and bundletool 1.18.3 validation passed. A bundle-generated universal APK verified against the same public signing certificate, package ID and version code. Its DEX and 62 assets match the published direct APK. The public certificate and AAB verification manifest are alongside the bundle.
- The normal entry point `powershell -File android/build.ps1 -Bundle` creates the APK, signed AAB and public certificate. Bundletool is pinned by its official SHA-256 digest and stored outside the repository in the local SoundLab build-tools directory.
- The generated download table and checksum catalog now cover eight release files. Evidence is in `working/EVIDENCE/play-bundle-2026-11-11/verification.json`.
- **BLOCKED · trusted Windows signing.** No code-signing certificate was available in the current-user or machine personal certificate stores. A trusted certificate or approved signing-service access is needed. SignPath Foundation's free open source signing requires application approval and verified build provenance. [Provider terms](https://signpath.org/terms.html)
- **NOT_TESTED · Play Console.** Enrollment, upload and Google acceptance require the intended developer account. AAB generation and local signing are complete.

## SoundLab identity release 2026.11.11.2 · 11 November 2026

- NTK selected a fresh Android release with ID `com.ntkhub.soundlabstudio`. The Java sources, export provider authority, certificate subject and keystore alias use SoundLab. This Android app has its own data and signer. Export media and session metadata from the earlier app before switching.
- The new private Android key is outside the project at `%LOCALAPPDATA%\NTKSoundLabStudio\android-signing\soundlab-release.p12`. The password is protected for the current Windows account. A repeated open of the existing key matched the APK's public certificate. No signing material is tracked or packaged. Google Play delivery still requires an AAB and enrollment.
- Current Windows program names, Linux executable and package, Go module, Python helper, JavaScript client, Laravel controller, current documentation and app data defaults use SoundLab. Previous desktop profiles, helper cookies, saved libraries, tutorial preferences and package upgrades have compatibility handling. Historical records contain their original names.
- **VERIFIED · distribution.** The seven rebuilt packages match the generated [checksum catalog](../../../SOFTWARE/SHA256SUMS.txt). Downloads and rollback paths are in the [release guide](../../../SOFTWARE/README-LATEST.md). The files are a local release candidate.
- **VERIFIED · application checks.** Windows Go tests, 13 Linux Go tests, four Python helper tests and 24 Laravel tests with 108 assertions passed. The Windows package passed 14 transcription checks, four codec and offline checks, three interaction checks and 25 karaoke checks. Additional browser checks covered earlier library reads, SoundLab writes and clearing both storage keys.
- **VERIFIED · Windows installer.** The exact setup installed in a clean offline Windows Sandbox. Upgrading the earlier setup used the SoundLab program path and preserved its profile fixture. Uninstall retained the fixture. Both Windows EXEs are unsigned.
- **VERIFIED · Linux core.** The AppImage launched through FUSE and extract-and-run in WSL. The extracted Debian core served the correct version and assets. Shutdown on the configured heartbeat timeout passed. The Debian package is `ntk-soundlab-studio` and declares replacement of the earlier package.
- **VERIFIED · offline and PHP.** The rebuilt Windows app imported the verified model and produced the reference four stems and instrumental after an offline reload in Edge using WASM on Intel Gen 9. The PHP archive migrated a fresh scratch database and passed app, health, runtime MIME and private-path checks.
- **PARTIAL · Android emulator.** The signed APK installed in airplane mode alongside the earlier Android app. The new SoundLab native navigation opened Transcribe offline. Android System UI errors covered the editor during the check, limiting further interaction. APK metadata, certificate, Java namespace, provider authority and shared assets match the fresh identity. Physical-device acceptance is open.
- **NOT_TESTED · remaining acceptance.** Physical-phone endurance, graphical Linux installation, WebGPU quality on other adapters, real singing recognition and live hosting require their target environments.

Evidence is in [rebrand-2026-11-11](../../EVIDENCE/rebrand-2026-11-11/). Work is based on commit `827b43fa2b528ce32ea70171505a0d01e35f5473` plus the preserved local maintenance changes.

## NTK SoundLab Studio 2026.11.11.1 maintenance candidate — 11 November 2026

- Candidate distribution and rollback paths are in [SOFTWARE/README-LATEST.md](../../../SOFTWARE/README-LATEST.md). The previous files remain available at their original paths. The desktop app origin and profile, Windows AppId, Debian package identity and Android application ID and signer carry forward.
- Transcript writes compare revisions in an IndexedDB transaction. A stale draft can be saved as a copy. Upload consent follows the recording and Groq key, and the new fingerprint covers every block of the file. Legacy partial records offer an explicit original-file confirmation.
- The Python helper requires a loopback session, restricts allowed assets and writes cookie data to private local configuration. The desktop proxy rejects HTML as upstream audio and limits provider redirects. Go and Python regression checks covered these boundaries.
- **VERIFIED · offline stems.** A clean browser profile imported the full verified model, reloaded offline, and produced four stems and a combined instrumental through the bundled ONNX Runtime Web 1.20.1. The Windows build repeated this with Microsoft Edge and a real Intel Gen 9 adapter. The app uses WASM on that adapter after WebGPU produced out-of-range samples on a quiet test clip. The WASM peaks matched the reference run. The model is a separate local file and publisher download.
- **VERIFIED · distribution.** Seven versioned files match the generated [SHA-256 catalog](../../../SOFTWARE/SHA256SUMS.txt). The candidate was built from local changes based on Git commit `827b43fa2b528ce32ea70171505a0d01e35f5473`. The previous files and their catalog are available for rollback.
- **VERIFIED · Windows and Linux cores.** The Windows Sandbox installed the exact setup in a clean offline guest, upgraded from the previous installer, and uninstalled while retaining a synthetic profile. WSL served the exact release core and assets from the AppImage using both FUSE and extract-and-run, and from the unpacked Debian archive. All three Linux test processes shut down on the configured heartbeat timeout.
- **VERIFIED · transcription memory.** Three sequential one-hour PCM jobs in the Windows build before the Intel graphics fix each processed 15 windows with a simulated provider. The preview, file and decoder references were released after each completed job. Sampled renderer working sets after garbage collection ranged from 161.6 to 165.3 MiB across the three jobs. The final build changed only the stem engine among the shared assets and passed the packaged browser suites again.
- **VERIFIED · packaged browser regressions.** The exact Windows portable passed 14 transcription checks, four format and offline checks, three mobile and recovery checks, and 25 karaoke checks. The browser tests used synthetic data and simulated recognition. Both Windows EXEs are unsigned.
- **VERIFIED · packaged PHP smoke.** Laravel 13 migrated a new scratch SQLite database. The packaged app and health endpoint returned HTTP 200, configuration paths returned 404, and anonymous cookie access returned 403. The updated production Symfony packages were present. Composer's locked audit returned zero advisories. The Linux and Windows Go tests, three Python helper tests, and 24 Laravel tests with 108 assertions passed.
- **PARTIAL · Android.** The final APK carries the previous signer and installed over the existing QA app in airplane mode. The library rendered. An Android System UI error interrupted the native Transcribe test. The offline editor and phone endurance still need runtime evidence.
- **NOT_TESTED · release acceptance.** Graphical Linux launch, WebGPU quality on other adapters, real Groq singing accuracy and actual AlwaysData hosting remain open.

Local QA evidence is in [maintenance-2026-11-11](../../EVIDENCE/maintenance-2026-11-11/). The [release guide](../../../SOFTWARE/README-LATEST.md) points to the exact downloads and previous release.

## Previous release · dedicated Transcribe — 2026.11.3.1

NTK authorized the dedicated workflow with **both 1 hour and 150 MB limits**.
Shared web/Windows/Linux/Android source and packages now include audio/video
import, automatic/manual language choice, speech/singing recognition, editable
text, local history/delete, copy, TXT/SRT/LRC downloads, progress, Cancel and
explicit retry. Android has a Transcribe bottom tab and native Files/Share output.

Groq Whisper is the initial online recognizer. Original language only; translation
and speaker labels are deferred. Upload requires explicit free-account/billing
confirmation; account eligibility is not inferred from a model name. No real
provider calls or paid fallback were used during development. AI request abort
composition was repaired for the shared helper.

Bounded decoding uses pinned MediaBunny 1.65.0 (MPL-2.0, bundled license/source URL)
and lazy Blob reads. Four-minute cores with two-second margins become mono16k WAV
uploads under8MB. Word midpoint ownership removes overlap duplication without
textual deduplication of repeated phrases. Decode capability is checked; unsupported
codecs fail with a WAV recovery option. No whole-hour decodeAudioData fallback.

Transcripts use separate IndexedDB NTKTranscriptsDB, preserving them across media
cache purges. Source recordings and credentials are not stored in transcript rows.
Completed sections/edits save locally; quota failures remain visible and edits are
kept for download. After reopening, select a partial transcript and the same source
file (name/size/mtime + first/last64KB digest) to resume. Changed line counts disable
timed exports; TXT preserves arbitrary edits. Closing/backgrounding cancels uploads.

VERIFIED:14 focused browser checks include a real115.2MB one-hour WAV through15
bounded windows, simulated429 and retry, consent, edits, downloads, reload/history,
cancellation, repeated phrases, storage failure and mobile fit. Three additional
checks cover double start, modal layering and protecting unsaved edits. Real48kHz
stereo WAV, MP3 and MP4 decode/downsample passed; PWA offline reload/history passed.
The25 existing karaoke checks passed on the packaged Windows server, including a
real short video render. Final Windows/AppImage/Debian runtime smoke checks each
confirm5 asset hashes plus actual decoding/recognition orchestration/local save.
Linux Go tests passed. Android emulator passed5 engine/lifecycle checks; TXT was
saved through Android Files and read back. Installed APK matches delivered hash.
Final desktop/mobile/Android screenshots were visually reviewed.

Package parity covers49 shared assets, both Blade views, APK assets (native index
adaptations excepted), static/Laravel ZIP CRC/hashes, runtime-data exclusions and
production-only Composer metadata. No backend/runtime data or live web deployment
was changed. Latest paths are in SOFTWARE/README-LATEST.md and SHA256SUMS.txt.
Windows portable/setup filenames are stable; Android uses android.2; Linux/static
archives use2026.11.3.1. Older versioned releases remain available for rollback.

NOT_TESTED: real recognition/accuracy with an eligible account; physical-phone
one-hour memory/thermal behavior; graphical Linux install/uninstall/FUSE and Windows
installer install/uninstall. Emulator and headless runtime checks are not those
acceptance tests. No universal bug-free claim is made.

Evidence: working/EVIDENCE/transcribe-2026-11-03, especially release-manifest.json,
transcribe-results.json, karaoke-results.json, format-offline-results.json,
extra-results.json, android-results.json, *-results.json and android-native-export.txt.
Source/replaced release backups: its backup/ tree; desktop build-backups; web
DEPLOY_MANUAL/package-backups (older historical ZIPs may contain private runtime).
Restore reviewed files without replacing user profiles/databases. No destructive
rollback or user-data migration was performed.

The sections below describe previous releases and their historical evidence.

## Android and Linux additions — 3 November 2026

NTK requested an Android APK that feels/behaves like a mobile app, plus Linux
AppImage and Debian packages. These local packages are now built and verified
within the scope below. The earlier Windows/web repair remains preserved below.

- Android release: `SOFTWARE/ANDROID/OmniStreamStudio-2026.11.3-android.1.apk`.
  Android10+, native navigation/pickers/dialogs/Save/Share/Back around the shared
  WebView studio engine. Mobile editor is first, appearance is expandable,
  library cards are compact, keyboard/insets are handled, and first launch is offline.
  Stable application ID/origin/signing identity preserves local storage across updates.
- Linux: `SOFTWARE/LINUX/OmniStreamStudio-2026.11.3-x86_64.AppImage` and
  `SOFTWARE/LINUX/omnistream-studio_2026.11.3-1_amd64.deb`. Both contain the same Go
  executable/shared frontend. A current installed Chromium/Chrome/Edge/Brave is
  required for app-window operation; xdg-open is the documented fallback.
- Android VERIFIED: signed/aligned package, exact44 bundled-file parity, actual
  Android15/WebView124 offline launch, native audio import, lyric persistence across
  recreation/update,11 engine/storage assertions, LRC Save with correct suffix,
  Android share chooser, and a real three-second VP9/Opus video saved through Files.
  Eight isolated mobile UI checks also passed. The exact delivered release was
  installed after a fresh emulator boot and visually checked in airplane mode:
  saved lyrics persisted, the first line is visible beneath the sticky tabs, and
  Back correctly highlights Library. The installed APK hash matches the delivered
  package. See Android VERIFICATION.md and `final-apk-back-library.png`.
- Linux VERIFIED:11 native Linux Go test groups,25 browser checks per final package
  in Linux Chromium156, short real video exports, AppImage extract-and-run, Debian
  payload execution, root ownership/modes, identical payload binaries and hashes.
  Windows Go tests/vet still pass after splitting platform-specific launchers.
- PARTIAL/NOT_TESTED: physical phones/ARM, Android10 minimum runtime, long renders,
  accessibility acceptance, full Linux graphical install/menu/uninstall/FUSE mode,
  real singing recognition and neural inference. A detached one-second Android
  canvas probe failed; a connected three-second studio export passed. The emulator
  is a developer OS and still exposes WebView inspection despite the non-debuggable
  release manifest and release disabling call; production-device inspection behavior
  is not verified. No stores, accounts, production deployment or paid calls were used.

Source: `android/` and `desktop/linux/`; build/use guides are beside those sources
and copied beside releases. Evidence: `working/EVIDENCE/android-2026-11-03` and
`working/EVIDENCE/linux-2026-11-03`, each with `VERIFICATION.md` and a release manifest.
All delivery hashes are in root `SOFTWARE/SHA256SUMS.txt`.

Rollback: previous `desktop/main.go` in the Linux evidence `before-integration`;
desktop staging backups retained by the existing build script. No old Windows/web
deliverable was replaced. Android build stages are retained; its private signing
material is outside the repo under the local NTK app-data signing directory with
a Windows-account-protected password. Keep it private and preserve it for upgrades.
Do not distribute SDK/AVD/browser profiles or signing material. Local test emulator
and browser helpers are stopped after verification; installed free tools/isolated
AVD are retained for repeat testing. Root was the sole active-checkout writer.

## Earlier Windows and web repair

Prepared for NTK · NTK Hub · 3 November 2026 · version 2026.11.3

**Local implementation and package verification: VERIFIED for the checks below. Live production and real provider recognition: NOT_TESTED.** This is a bounded repair, not a claim that every possible application defect has been eliminated.

## Requested outcome

Use the lyrics already present in Live Lyrics Editor to synchronize Karaoke Video Studio to the sung audio. Apply the repair across the portable Windows app, installer and web sources/packages, and fix discovered defects. No live publishing, paid calls, account changes, database migration or user-profile migration was performed.

## What changed

- The editor is read directly at the start of Auto-Sync, including intentionally empty text and short lines such as “Oh”. Supplied wording and repeated choruses are preserved. Existing timestamps are replaced using provider word timestamps; empty input requests transcription.
- The alignment algorithm requires complete, unambiguous normalized matching. Missing/reordered/ambiguous words or invalid timestamps preserve the editor and show an error. It is transcript matching, not acoustic forced alignment; it cannot guarantee that a provider recognized singing correctly.
- Word timings persist with exact source text and decoded audio duration; preview, render and subtitles use the matching data. Manual edits invalidate old timing. Cached vocals can be used for recognition; selected master/vocal/instrumental playback now reads the actual saved stem fields.
- Fixed canvas text-wrapper accumulation, zero-value settings, stale subtitle text, short-track cue overflow, timestamp rounding, mismatched imported cues, pending-preview/song-switch races and cancelled renders falsely reporting partial success. Lyrics import/reset/search now persist and reject stale updates.
- Free Only allowlists and explicit audio-upload confirmation replace unconditional billing claims. No paid fallback is invoked. Existing legacy keys migrate to IndexedDB only after durable writes; keys are not duplicated in localStorage. Browser key storage is not application-encrypted.
- Hosted pages cannot silently call loopback helpers. URL classification checks actual hosts and preserves signed direct-media query parameters. Download POSTs are not replayed after uncertain network failures. Imports reject unsafe identifiers/URL schemes; stale async operations cannot overwrite newer edits.
- Desktop now uses stable loopback port 47831 and the existing durable profile location. Refresh does not shut down the server. APIs require a random HttpOnly session and matching Host/Origin. Public-only checked DNS dialing, redirect limits, truthful capabilities and errors replace unsafe proxying and fake job progress. Conversion jobs were never implemented in the former portable wrapper; they now clearly report unavailable.
- Laravel uses pinned public DNS, verified TLS, checked redirects, bounded downloads, failed-output cleanup, restricted FFmpeg inputs and active-read/prune locking. Cookie administration fails closed without a header key. Hosted arbitrary extraction requires separately enforced public-only egress; ordinary shared hosting leaves it disabled. Unbounded passthrough is disabled. Suno transfers use bounded temporary storage with one concurrent transfer.
- Fixed PHP minimum to 8.4.1, cleaned `.env.example`, synchronized both Blade views and all public assets, and replaced the unsafe ZIP builder. Packages exclude real environment files, databases, cookies, sessions, logs, caches, test/evidence trees and development dependencies. Old releases are retained for rollback.

## Evidence

Paths below are relative to `working/EVIDENCE/repair-2026-11-02`.

| Check | Result | Evidence |
|---|---|---|
| Alignment rejection/preservation/Unicode/repetition tests against active module | 24 passed | `alignment-work/test-lyric-alignment.cjs` |
| Browser editor-to-AI-to-preview/subtitles and complete short MediaRecorder export | 25 passed against final embedded EXE | `final-desktop/lyrics-results.json` |
| Key migration, paid-route rejection, provider 429, malicious imports, cancellation, loopback policy, subtitle/URL integrity | 8 groups passed | `alignment-work/frontend-extra-results.json` |
| Offline service worker, own-cache isolation, editor persistence, desktop/mobile reachability | 13 passed | `release-checks/offline-ui-results.json` |
| Windows native HTTP/security/lifecycle tests | 20 passed on isolated same-core build | `desktop-work/native-qa-results.json` |
| Windows native relaunch and real IndexedDB/localStorage persistence | 10 passed on rebuilt Windows binary | `final-desktop/browser-native-results.json` |
| Desktop Go tests, vet, Windows GUI compilation | Passed | `desktop/main_test.go`, `desktop-work/INTEGRATION.md` |
| Laravel suite including real FFmpeg conversion | 25 passed, 109 assertions in isolated tree | `laravel-work/backend-results.xml` |
| Packager rejection/exclusion/rollback tests | 6 passed | `release-checks/test_packager.py`, `release-checks/INTEGRATION.md` |
| Extracted production Laravel ZIP boots and completes editor/preview/subtitle/video workflow | 25 browser checks passed | `web-package-browser-results.json` |
| ZIP CRC, per-file hashes, runtime exclusion and production dependency metadata | Passed | `web-package-checks.json` |
| Packaged Composer classmap completeness | 4,852 class files present, zero missing | Extracted-package PHP classmap check |
| Source/desktop/web asset parity and artifact hashes | See final manifest | `release-manifest.json`, root `SOFTWARE/SHA256SUMS.txt` |

All browser/provider tests used synthetic audio/transcript responses and disposable profiles. External browser traffic was blocked. The short video render was real MediaRecorder output, not a mock. Provider account eligibility, real sung audio recognition, real Suno/third-party downloads, native installer installation/uninstallation, the Edge app-window launch path, Linux native and Android native execution remain NOT_TESTED. Neural runtime/model inference is also NOT_TESTED and not bundled for first-launch offline use.

## Source and deliverables

Workspace root: `C:\Users\NTK\Downloads\Suno Downloader`.

- Canonical frontend: `working`; its Git branch is `main`, baseline HEAD `88a2c75876b256d6ffe6c711a8a3fe773b20b0e7`. Valid preexisting dirty changes were retained. No commit or push was made.
- Desktop source/build: `desktop`; Laravel source: `laravel`.
- Portable: `SOFTWARE/PORTABLE/WINDOWS/OmniStreamStudio-Portable.exe` (also `dist`).
- Installer: `SOFTWARE/INSTALLERS/WINDOWS/OmniStreamStudio-Setup.exe` (also `dist`).
- Static web: `SOFTWARE/WEB/OmniStreamStudio-Static-2026.11.3.zip`.
- Laravel web: `DEPLOY_MANUAL/NTK_OmniStream_Studio_AlwaysData.zip`; read the revised adjacent deployment guide. No live site was updated.

## Preservation and recovery

The final extracted-package check caught and corrected an overly broad vendor-directory exclusion: production dependencies use `helper` and `Test` as runtime source folders. The packager preserves those while excluding actual project evidence and dependency test suites. Regression fixtures now cover both folder names. Initial failed QA runs were confined to disposable package copies; the final packaged web workflow passed.

The actual Laravel `.env`, database, private storage and real Edge profile were not migrated or intentionally modified. The repaired app retains `%LOCALAPPDATA%\NTKOmniStreamStudio\profile`; **old data stored under random localhost ports remains in that profile but is not automatically migrated to the new fixed origin**. Do not delete it. Recovery can use the new executable's `--port OLD_PORT` option for a known old origin, followed by reviewed export/import; do not guess or overwrite browser databases.

Before-repair files and prior executables are under `working/EVIDENCE/repair-2026-11-02/backup`. Desktop stage/build rollback is under `desktop/build-backups`; previous web ZIPs are under `DEPLOY_MANUAL/package-backups`. Old web ZIPs may contain runtime/credential material from the former packager; keep them private and do not redistribute. Restore reviewed source/binaries from these backups without replacing user data. No destructive rollback test was performed.

## Runtime and dependencies

Windows/PowerShell, Codex root as sole active-checkout writer; subagents used isolated copies or read-only reviews. No separate agent/model routing recommendation was made. PHP 8.4.24, Laravel 13.39, PHPUnit 12.5.42, Chromium 153 and local FFmpeg were used. Laravel Boost and its five total development dependency additions fulfilled the repository bootstrap instructions; production dependencies are installed separately without dev packages. No paid services or production infrastructure were used.

See `TASKS.md`, `DECISIONS.md` and `NEXT_AGENT.md` for the remaining verification boundary and continuation.
