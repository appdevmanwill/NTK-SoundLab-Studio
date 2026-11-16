#!/bin/sh
set -eu
# Run inside Linux. The Go binary must be built for linux/amd64 with CGO_ENABLED=0.
# Usage: package-linux.sh BINARY ICON APPIMAGETOOL RUNTIME OUTPUT_DIRECTORY
[ "$#" -eq 5 ] || { echo 'Expected binary, icon, appimagetool, runtime and output directory' >&2; exit 2; }
binary=$(realpath "$1")
icon=$(realpath "$2")
tool=$(realpath "$3")
runtime=$(realpath "$4")
mkdir -p "$5"
output=$(realpath "$5")
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
version=2026.11.16.4
appimage_name="NTKSoundLab-$version-x86_64.AppImage"
deb_name="ntk-soundlab_${version}-1_amd64.deb"
# Use Linux storage for permissions; Windows-mounted workspaces report mode 777.
stage=$(mktemp -d "${TMPDIR:-/tmp}/ntk-soundlab-package-XXXXXXXX")
appdir="$stage/NTKSoundLabStudio.AppDir"
debdir="$stage/debian"
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/applications" "$appdir/usr/share/icons/hicolor/192x192/apps" "$appdir/usr/share/doc/ntk-soundlab-studio"
install -m 755 "$binary" "$appdir/usr/bin/ntk-soundlab-studio"
install -m 644 "$icon" "$appdir/ntk-soundlab-studio.png"
install -m 644 "$icon" "$appdir/usr/share/icons/hicolor/192x192/apps/ntk-soundlab-studio.png"
install -m 644 "$script_dir/README-LINUX.md" "$appdir/usr/share/doc/ntk-soundlab-studio/README.md"
install -m 644 "$script_dir/../../LICENSE" "$appdir/usr/share/doc/ntk-soundlab-studio/copyright"
cat > "$appdir/ntk-soundlab-studio.desktop" <<'DESKTOP'
[Desktop Entry]
Version=1.0
Type=Application
Name=NTK SoundLab Studio
GenericName=Audio and Karaoke Studio
Comment=NTK Hub local audio editing, lyrics and karaoke video studio
Exec=ntk-soundlab-studio
TryExec=ntk-soundlab-studio
Icon=ntk-soundlab-studio
Terminal=false
Categories=AudioVideo;Audio;Video;AudioVideoEditing;
Keywords=music;lyrics;karaoke;audio;video;NTK;
StartupWMClass=NTKSoundLabStudio
DESKTOP
cp "$appdir/ntk-soundlab-studio.desktop" "$appdir/usr/share/applications/ntk-soundlab-studio.desktop"
ln -s ntk-soundlab-studio.png "$appdir/.DirIcon"
cat > "$appdir/AppRun" <<'APPRUN'
#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$root/usr/bin/ntk-soundlab-studio" "$@"
APPRUN
chmod 755 "$appdir/AppRun" "$tool" "$runtime"
if command -v desktop-file-validate >/dev/null 2>&1; then desktop-file-validate "$appdir/ntk-soundlab-studio.desktop"; fi
# The pinned runtime prevents packaging from downloading a different one silently.
ARCH=x86_64 VERSION="$version" APPIMAGE_EXTRACT_AND_RUN=1 "$tool" --runtime-file "$runtime" --comp zstd "$appdir" "$stage/$appimage_name"
(
    cd "$stage"
    "./$appimage_name" --appimage-extract usr/bin/ntk-soundlab-studio
    cmp "$binary" squashfs-root/usr/bin/ntk-soundlab-studio
)
mkdir -p "$debdir/DEBIAN"
cp -a "$appdir/usr" "$debdir/usr"
size=$(du -sk "$debdir/usr" | cut -f1)
cat > "$debdir/DEBIAN/control" <<CONTROL
Package: ntk-soundlab-studio
Version: $version-1
Section: sound
Priority: optional
Architecture: amd64
Maintainer: NTK Hub
Installed-Size: $size
Conflicts: omnistream-studio
Replaces: omnistream-studio
Provides: omnistream-studio
Depends: ca-certificates, xdg-utils
Recommends: google-chrome-stable | chromium | chromium-browser | microsoft-edge-stable
Description: NTK Hub audio and karaoke studio
 Local audio importing, lyrics editing, mastering and karaoke video export.
 Uses an installed Chromium browser in a dedicated app window and profile.
 Other installed default browsers can open the stable local URL as a fallback.
 No remote service or account is required for core local editing.
CONTROL
find "$debdir" -type d -exec chmod 755 {} +
find "$debdir" -type f ! -path '*/bin/ntk-soundlab-studio' -exec chmod 644 {} +
dpkg-deb --root-owner-group --build "$debdir" "$stage/$deb_name"
# Retain previous releases beside the current output instead of deleting them.
for name in "$appimage_name" "$deb_name"; do
    if [ -e "$output/$name" ]; then mv -- "$output/$name" "$stage/previous-$name"; fi
    cp -- "$stage/$name" "$output/$name"
done
chmod 755 "$output/$appimage_name"
cp "$script_dir/README-LINUX.md" "$output/README-LINUX.md"
sha256sum "$output/$appimage_name" "$output/$deb_name"
echo "Preserved packaging stage: $stage"
