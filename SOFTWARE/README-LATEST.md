# Install SoundLab

The current preview is **2026.11.16.1**. Get the files from the [GitHub release](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/tag/v2026.11.16.1).

## Windows

Download `NTKSoundLab-Setup-2026.11.16.1.exe` for an installer, or `NTKSoundLab-Portable-2026.11.16.1.exe` to run a single executable.

Microsoft Edge must be installed. Python, Node.js, Go and FFmpeg are build or optional-helper tools and are unnecessary for local editing in the packaged app.

Both Windows files are unsigned. An unknown-publisher warning is expected.

The installer uses a per-user directory under `%LOCALAPPDATA%\Programs\NTK SoundLab Studio`. Fresh app data goes under `%LOCALAPPDATA%\NTKSoundLabStudio`. An existing desktop profile is detected and opened in place during an upgrade.

## Android

Download `NTKSoundLab-2026.11.16.1.apk` and open it with Files on an Android 10 or later device. Android may ask you to allow installation from the app you used to open the file. Keep Android System WebView updated.

This release uses `com.ntkhub.soundlabstudio` and installs separately from the earlier Android app. Export recordings and session metadata from that app before switching. Future SoundLab updates use the new ID and its SoundLab signer.

Use the AAB if you are preparing a Play Console release. The public upload certificate is included on the release page. Play App Signing setup and store acceptance are still pending. [Android build and signing notes](../android/README.md)

## Linux

Use the AppImage for a single downloadable file, or the `.deb` for Debian and Ubuntu. Both need an installed browser. [Linux instructions](LINUX/README-LINUX.md)

## Web and PHP hosting

The static ZIP contains the browser app. Extract it and serve the files over HTTPS or localhost. A web server is required for browser storage, modules and offline caching.

The AlwaysData ZIP contains the Laravel backend, production PHP dependencies and browser assets. It needs PHP 8.4.1 or later within the supported Composer range. [PHP setup](../DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md)

## Check a download

Download `SHA256SUMS.txt` from the release page into the same folder as the release files.

On Windows, calculate a file's hash and compare it with the matching line.

```powershell
Get-FileHash .\NTKSoundLab-2026.11.16.1.apk -Algorithm SHA256
```

On Linux, when all listed files are in the download folder, run the following command.

```sh
sha256sum --check SHA256SUMS.txt
```

Missing files are reported if you downloaded only part of the release.

## Offline use and saved work

Import the optional model through **Offline Storage** before using neural stems without a connection. [Model instructions](OFFLINE_MODELS/README.md)

Projects and transcripts are saved in the current app or browser profile. Export important results to your own files. Session JSON keeps metadata and lyrics, so save the media separately.

The release notes list what was tested and what still needs device or hosting checks. Earlier repository files are available in Git history for recovery.
