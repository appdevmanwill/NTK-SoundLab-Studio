# NTK SoundLab Studio

SoundLab is an audio and karaoke editor for Windows, Linux, Android and the web. Import a recording, trim or mix it, add lyrics, and export audio or a lyric video.

It also has optional stem separation and transcription. Editing runs on your device. Transcription sends audio to your chosen provider after you confirm the upload.

Built by NTK for NTK Hub.

## Download

The current desktop preview is **2026.11.16.4**, which opens in Chrome on Windows and prefers Chrome on Linux. The Chrome, Firefox, Opera and Edge grabbers also use release **2026.11.16.4**. Android, web and PHP use **2026.11.16.3**. Start with the Windows installer or Android APK if you want to use the app. The AAB is for publishing through Google Play.

<!-- release-downloads:start -->

| Platform | Download |
| --- | --- |
| Windows x64 | [Portable EXE](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Portable-2026.11.16.4.exe) |
| Windows x64 | [Setup installer](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Setup-2026.11.16.4.exe) |
| Linux x64 | [AppImage](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-2026.11.16.4-x86_64.AppImage) |
| Linux x64 | [Debian package](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/ntk-soundlab_2026.11.16.4-1_amd64.deb) |
| Android 10+ | [APK](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-2026.11.16.3.apk) |
| Web | [Static PWA ZIP](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Static-2026.11.16.3.zip) |
| PHP hosting | [AlwaysData ZIP](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTK_SoundLab_Studio_AlwaysData-2026.11.16.3.zip) |
| Google Play | [Signed AAB](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-2026.11.16.3.aab) |
| Chrome | [Media Grabber ZIP](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Browser-Grabber-Chrome-2026.11.16.4.zip) |
| Firefox | [Media Grabber ZIP](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Browser-Grabber-Firefox-2026.11.16.4.zip) |
| Opera | [Media Grabber ZIP](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Browser-Grabber-Opera-2026.11.16.4.zip) |
| Edge | [Media Grabber ZIP](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v2026.11.16.4/NTKSoundLab-Browser-Grabber-Edge-2026.11.16.4.zip) |

<!-- release-downloads:end -->

[Release notes and all files](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/tag/v2026.11.16.4) Â· [Checksums](SOFTWARE/SHA256SUMS.txt) Â· [Setup guide](SOFTWARE/README-LATEST.md)

Windows needs Google Chrome. Linux needs an installed browser such as Chromium, Chrome, Edge or Brave. Android requires Android 10 or later and an updated System WebView. The Windows files are unsigned, so Windows may show an unknown-publisher warning.

## Browser media downloads

The [Media Grabber](extension/README.md) saves original files, MP3 at 320 kbps, 24-bit WAV, and supported video/HLS streams. **Save video** keeps the picture and sound; **Edit audio in SoundLab** extracts audio for editing. **Record playback with sound** handles animated pages and storyboards, including previews such as Atlabs. Recording re-encodes the selected tab at its visible resolution.

Downloads depend on the source, browser and codec. Converting compressed audio to WAV does not restore missing detail. DRM and DASH downloads are unsupported. Firefox requires temporary installation until Mozilla signing is completed.

## First session

1. Open SoundLab and choose **Import Video or Audio**. On Android, tap **Import audio or video**.
2. Select a short file from your device. Its card in the library gives you the audio, trim, stem and video tools.
3. Open **Trim & FX** to cut a section or apply an effect. Use the audio export controls to save WAV or MP3.
4. For a lyric video, open **Video Studio**, add or import lyrics, adjust the timing, and preview before exporting.

Video formats depend on the browser or WebView. A file that fails to import may need converting to WAV or a supported video format first.

## Stems and transcripts

**Stem separation** uses HTDemucs to produce vocals, drums, bass and other instruments. The app can also combine the backing tracks into an instrumental. Results depend on the recording, and vocals can still bleed into other stems.

For browser processing, import the optional model under **Offline Storage**. The matching runtime ships with the app. The model is about 180 MB and is downloaded separately from its publisher. [Offline model setup](SOFTWARE/OFFLINE_MODELS/README.md)

**Transcribe** accepts audio or video up to one hour and 150 MB. It uses your Groq key and uploads the audio in sections. You can cancel, keep completed sections, edit the saved text, and export TXT, SRT or LRC. Recognition needs internet access and an eligible provider account. Singing accuracy has not yet been measured against reference lyrics.

## What stays on the device

Local imports, trimming, mixing, effects and video rendering run on the device. Saved projects, transcripts and cached media belong to that app or browser profile.

Remote links, model downloads and optional AI tools use the network. The web version can also request fonts. The app asks for confirmation before transcription uploads. A provider key does not establish that an account has free capacity, so check the account's billing and quota settings.

Save important exports outside the app. Session JSON contains metadata and lyrics. Keep separate copies of the audio and video files.

## Link imports & Browser Media Grabber

The packaged desktop app, web/PHP backend, and Python helper support Suno AI, ACE Music, Flow Music / Riffusion / Producer.ai, Treblo / Sonauto, Audius, Vocaroo, and direct public media URLs (`MP3`, `WAV`, `OGG`, `FLAC`, `M4A`, `AAC`, `MP4`, `WebM`, plus Vimeo metadata). General extractors (YouTube, SoundCloud, TikTok, Instagram, X, Mixcloud, and HLS `.m3u8`/`.mpd`) require the optional local Python helper (`yt-dlp`) or a configured server extractor.

When a page uses per-session browser tokens or dynamic in-memory players (such as Audiomack in your signed-in Chrome or Edge tab), install the **NTK SoundLab Media Grabber** extension ([extension guide](extension/README.md)) or use the in-app **Browser Grabber** modal / Universal Bookmarklet to capture the playing unencrypted `audio/*` or `video/*` stream and import it straight into SoundLab Studio. DRM-protected playback streams cannot be extracted.

A link working in a normal browser does not guarantee that SoundLab can download it. Local file import is the most predictable starting point.

## Current test coverage

The Windows installer was checked in a clean offline Sandbox, including upgrade and uninstall with a saved profile fixture. AppImage and Debian cores were checked under WSL. Browser checks covered audio decoding, transcript saving, exports and karaoke rendering. The signed Android bundle was validated, and its generated APK matched the direct APK's code and assets.

The Android APK opened the editor offline in an emulator, but Android System UI errors limited further interaction. Physical-phone endurance, graphical Linux installation, real singing transcription and production PHP hosting still need testing.

## Working on the source

The shared browser app is in `working/`. The platform wrappers and backend are in `desktop/`, `android/` and `laravel/`.

- [Run and develop the browser app](working/README.md)
- [Build Android packages](android/README.md)
- [Linux installation and packaging](desktop/linux/README-LINUX.md)
- [Run the Laravel backend](laravel/README.md)
- [Deploy the PHP package](DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md)

## License

SoundLab's own code is MIT licensed. Bundled libraries and the optional model have their own terms. [Project license](LICENSE) Â· [Third-party notices](working/THIRD_PARTY_NOTICES.md)
