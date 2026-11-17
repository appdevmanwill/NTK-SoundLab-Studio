# Project Operating Intelligence — NTK SoundLab Studio

> **Scope:** Project-specific operational standard for `NTK SoundLab Studio`. Complements the global NTK Operating Standard (`~/.gemini/config/AGENTS.md`).

---

## A. Project Identity
- **Project Name:** NTK SoundLab Studio (Short Name: `NTK SoundLab`)
- **Purpose:** Universal multi-platform media downloader, client-side video demuxer, Meta HTDemucs v4 2-stem/4-stem neural stem separator, 5-track synchronized audio mixing console, waveform trimmer, mastering FX, and 1080p karaoke visualizer video generator.
- **Primary Users:** Music producers, vocalists, remixers, karaoke creators and digital media editors using local processing with optional provider-based recognition.
- **Current Phase:** GitHub preview v2026.11.17.1 for Media Grabber 1.2.0 and additional Linux packages. The Windows and original Linux downloads use 2026.11.16.4 and Android/web/PHP use 2026.11.16.3.
- **Latest Verified Milestone:** Added extension editing and offline HTDemucs separation, verified captured MP4 import and core trim/tag workflows on installed desktop browsers, and expanded Linux delivery with RPM, ARM64 DEB, portable archives and Flatpak. All 20 uploaded GitHub assets matched local SHA-256 and sizes. See working/docs/handoff/CURRENT_STATE.md for the outstanding device and store checks.
- **Authoritative Source References:** `README.md`, `SOFTWARE/README-LATEST.md`, `DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md`.

---

## B. Verified Technology Stack
- **Frontend / PWA:** Vanilla modern JavaScript (ES6+), Web Audio API, Web Workers, IndexedDB (v2 vault), lamejs (MP3 320kbps), HTML5 Canvas visualizer.
- **Backend / API:** Laravel 13 with PHP `^8.4.1`, plus an optional Python helper for yt-dlp and PyTorch HTDemucs.
- **Desktop Runtime:** Go launcher with a dedicated system-browser profile on Windows and Linux, and Inno Setup 6 for the Windows installer.
- **Mobile Target:** Java/WebView shell, Android platform 36.1 and build-tools 36.1.0, minimum Android 10, target API 36. The current APK has a v3 signature using RSA-3072.
- **Packaging:** AppImageKit (`appimagetool`), `dpkg-deb` (WSL Ubuntu-26.04), Inno Setup (`ISCC.exe`).
- **Hosting / Distribution:** Firebase Hosting (Spark $0 plan), AlwaysData PHP hosting, GitHub Releases / Repositories.

---

## C. Development Environment
- **Selected Environment:** Hybrid Native Windows + WSL (Ubuntu-26.04) for Linux builds.
- **Rationale:** Native Windows delivers fastest Go compilation and Inno Setup execution; WSL provides native `dpkg-deb` and `appimagetool` packaging without overhead.
- **Verified Daily Commands:**
  ```bash
  # Go Desktop Test & Build
  cd desktop
  go test ./...
  go build -ldflags "-s -w -H windowsgui" -o ../dist/NTKSoundLab-Portable.exe .

  # Windows Installer (Inno Setup)
  "C:\Users\NTK\AppData\Local\Programs\Inno Setup 6\ISCC.exe" desktop/installer.iss

  # Linux Packaging (WSL) — tools live in %LOCALAPPDATA%\NTKSoundLabStudio\build-tools\
  powershell -File desktop/linux/build.ps1 -AppImageTool "$env:LOCALAPPDATA\NTKSoundLabStudio\build-tools\appimagetool-x86_64.AppImage" -AppImageRuntime "$env:LOCALAPPDATA\NTKSoundLabStudio\build-tools\runtime-x86_64" -OutputDirectory "$PWD\SOFTWARE\LINUX"

  # Android APK Build
  cd android
  powershell -ExecutionPolicy Bypass -File build.ps1

  # Firebase Deploy
  cd working
  firebase deploy --only hosting
  ```

---

## D. Architecture & Core Policy
- **100% Client-Side Privacy:** Audio demuxing, waveform processing, FX mastering, and video rendering happen entirely within the user's browser or desktop environment.
- **Smart PWA Detection:** PWA install action is only presented when running inside a web browser; suppressed in Desktop and Android builds.
- **Free-First Budget:** $0 budget strictly maintained across all builds, tools, and hosting.
