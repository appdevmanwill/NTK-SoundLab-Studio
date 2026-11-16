# NTK SoundLab Studio for Linux

NTK Hub · 2026.11.16.1 · x86_64 / amd64

The shared studio and local Go service are bundled. Install a current Chromium,
Chrome, Edge or Brave browser for the dedicated app window. The browser is not
included in either package. A default-browser fallback uses xdg-open when no
supported Chromium browser is found; its storage belongs to that browser.

## AppImage

Make the file executable in your file manager's Properties / Permissions dialog,
then double-click it. Or run:

```sh
chmod +x NTKSoundLab-2026.11.16.1-x86_64.AppImage
./NTKSoundLab-2026.11.16.1-x86_64.AppImage
```

If the system cannot mount AppImages using FUSE, run without FUSE:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 ./NTKSoundLab-2026.11.16.1-x86_64.AppImage
```

The extract-and-run mode uses temporary disk space. Neither mode requires root.

## Debian / Ubuntu package

```sh
sudo apt install ./ntk-soundlab_2026.11.16.1-1_amd64.deb
```

Open **NTK SoundLab Studio** from the applications menu. The package declares
ca-certificates and xdg-utils dependencies and recommends a Chromium browser.
Use the AppImage if you do not want system installation.

## Your data and offline use

- The service listens only on `127.0.0.1:47831`. Keep this port stable; browser
  storage belongs to this origin. Another running instance or port conflict
  produces an error instead of silently switching to an empty library.
- Fresh installs use `$XDG_CONFIG_HOME/NTKSoundLabStudio/profile` (normally
  `~/.config/NTKSoundLabStudio/profile`). Upgrades detect and reopen the earlier
  profile in place. Settings, songs, media and provider keys are local browser
  data. Keep a private backup of the profile while the app is closed.
- Core importing, editing, local playback and supported exports work offline
  with the required browser installed. Online links, optional fonts, AI providers
  and model downloads require connectivity. AI is off by default. Optional
  neural weights can be imported from Offline Storage. The matching runtime is
  bundled. Actual singing recognition depends on the provider's timestamps.
- Closing the last app window stops the service after its 90-second heartbeat
  grace period. Refreshing the app preserves the service and saved library.
- The Linux package uses the same repaired lyric editor and karaoke engine as
  the Windows/web releases. Supported formats and render speed depend on your
  browser and hardware. Start with a short 480p export when checking a new system.
- Direct media and supported Suno links use the local service. General site
  extraction and native FFmpeg conversion are not included in this wrapper.

## Recovery and removal

Export sessions and media from the studio before moving computers or browsers.
The JSON session holds metadata; it is not a backup of all cached audio/stems.
Back up the dedicated profile while the app and browser are closed. Keep old
AppImages for rollback. Do not run the app as root or disable browser sandboxing.

To remove the installed package, use `sudo apt remove ntk-soundlab-studio`. This
does not remove your home-directory profile. Delete an AppImage to remove that
copy; it likewise preserves data. Reinstalling/upgrading uses the same local
origin and profile. Switching to another browser does not automatically migrate
the first browser's stored library.

For a distro-specific Chromium executable, set `NTK_SOUNDLAB_BROWSER` to its
executable path. The value is a single path, not a shell command or flags.
For diagnostics, run `ntk-soundlab-studio --headless` in a terminal and open the
printed URL, or read `~/.config/NTKSoundLabStudio/desktop.log`. Never share
provider keys or private browser files in support reports.
