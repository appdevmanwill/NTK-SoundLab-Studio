# SoundLab for Android

The Android app wraps the shared studio in a native activity with navigation, Files integration and a share sheet. Editing runs in Android System WebView, and the bundled interface opens without a hosted website.

Android 10 or later is required. Keep System WebView updated.

## Install and use

Install the APK from the [release page](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/tag/v2026.11.11.2). Android may ask for permission to install files opened by your browser or Files app.

Tap **Import audio or video** to choose a recording. **Transcribe** opens the transcript editor. **Karaoke** opens the video tools, and **Tools** contains storage, optional provider keys and session import/export.

After an export, choose **Save a copy to Files** or **Share with another app**. Save important files before closing the session. Temporary exports older than 24 hours are cleaned up on a later launch.

Keep the app visible while rendering. Backgrounding pauses playback and cancels a running render. The initial video preset is 720p at 30 fps. Available output formats depend on WebView.

## Saved data and upgrades

The application ID is `com.ntkhub.soundlabstudio`. This app installs separately from the earlier Android package. Export media and session metadata from that app before switching.

Projects, cached media and provider keys are stored in app data. Clearing app data or uninstalling removes them. Android backup is disabled. Session JSON contains metadata and lyrics, so retain separate media files.

Recognition and remote link imports need internet access. Local editing works without an AI account. Browser stem processing also needs the optional imported model.

## Build on Windows

The current builder uses JDK 21, Python, Android platform 36.1 and build-tools 36.1.0. Set `JAVA_HOME` and `ANDROID_SDK_ROOT` if your installed tools use different directories.

Stage the frontend, then build the APK from the repository root.

```powershell
powershell -File desktop/build.ps1 -StageOnly
powershell -File android/build.ps1
```

Use `-DebugBuild` for emulator debugging. Use `-InitializeSigning` only when creating a new app signing identity. Routine updates reuse the existing key.

To build the signed Play bundle as well, run the following command.

```powershell
powershell -File android/build.ps1 -Bundle
```

That build requires `bundletool-all-1.18.3.jar` under `%LOCALAPPDATA%\NTKSoundLabStudio\build-tools`, or a path supplied with `-BundleToolPath`. The builder checks the JAR against the official release digest. [Bundletool 1.18.3](https://github.com/google/bundletool/releases/tag/1.18.3)

## Signing and Google Play

The builder keeps the private keystore outside the source tree at `%LOCALAPPDATA%\NTKSoundLabStudio\android-signing\soundlab-release.p12`. Its password is protected for the current Windows account by DPAPI. Keep a private, recoverable backup for future updates.

The release includes a signed AAB and its public upload certificate. The AAB passed local signature and bundle validation. Its generated APK matched the direct APK's signer, DEX and 62 bundled assets.

Play App Signing enrollment and Play Console acceptance still need the intended developer account. To keep compatibility with direct APK installs, provide the existing SoundLab app signing key through Google's encrypted transfer procedure during enrollment. [Android signing guide](https://developer.android.com/studio/publish/app-signing)

## Test status

The current APK installed alongside the earlier app and opened Transcribe offline in an API 35 emulator. Android System UI errors limited further interaction. Physical-phone endurance, large exports and real singing recognition still need testing.
