# SoundLab for Linux

| Computer | File to choose |
| --- | --- |
| Fedora on a 64-bit Intel or AMD computer | The x86_64 RPM |
| Debian or Ubuntu on a 64-bit ARM computer | The arm64 DEB |
| Another Linux distribution | The matching amd64 or arm64 portable archive |

If you are unsure which processor you have, open Settings and look under About. You can also run `uname -m`. Choose amd64 for `x86_64` or arm64 for `aarch64`.

Install Chrome or Chromium first. Install the package using your system's software installer, then open **NTK SoundLab Studio** from the applications menu. On Fedora the terminal equivalent is `sudo dnf install ./your-downloaded-file.rpm`. On Debian or Ubuntu use `sudo apt install ./your-downloaded-file.deb`.

For the portable archive, extract it, open its `usr/bin` folder and run `ntk-soundlab-studio`. If your file manager asks, allow the file to execute. Running it from a terminal in that folder also works with `./ntk-soundlab-studio`.

The Flatpak preview uses the desktop's default browser through the system portal. Its browser library belongs to that browser profile. Export your projects and media before switching installation methods. The browser app or existing AppImage remains an alternative on compatible systems.

To test a downloaded Flatpak bundle, install it with `flatpak install --user ./NTKSoundLab-2026.11.17.1-x86_64.flatpak`, then open **NTK SoundLab Studio**. It needs the Freedesktop 25.08 runtime from Flathub. Install the runtime first if prompted.

From the source checkout on the Windows build host, run `powershell -File desktop/linux/build-extras.ps1` with Go, Ubuntu WSL, RPM and Debian tools available. Add `-Flatpak` with Flatpak Builder and the Freedesktop Platform and SDK already installed in the WSL user account. The script packages the allowlisted frontend currently embedded in `desktop/assets`. Stage a reviewed frontend revision with `desktop/build.ps1 -StageOnly` before building if those assets need updating.

Check your installation by importing a short recording and exporting WAV. See the GitHub release for verification status and device limitations. Run on a normal user account so the browser can apply its sandbox.
