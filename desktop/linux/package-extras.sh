#!/bin/sh
set -eu

version=$1
binaries=$2
output=$(realpath "$3")
mode=$4
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(realpath "$here/../..")
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
icon=tech.ntkhub.SoundLabStudio

for arch in amd64 arm64; do
    name="NTKSoundLab-$version-linux-$arch"
    tree="$stage/$name"
    install -Dm755 "$binaries/soundlab-$arch" "$tree/usr/bin/ntk-soundlab-studio"
    install -Dm644 "$root/working/assets/icons/icon-192.png" "$tree/usr/share/icons/hicolor/192x192/apps/$icon.png"
    install -Dm644 "$here/$icon.desktop" "$tree/usr/share/applications/$icon.desktop"
    install -Dm644 "$root/LICENSE" "$tree/usr/share/doc/ntk-soundlab-studio/copyright"
    install -Dm644 "$here/README-EXTRA.md" "$tree/README.md"
    tar -C "$stage" -czf "$stage/$name.tar.gz" "$name"
    install -m644 "$stage/$name.tar.gz" "$output/$name.tar.gz"
done

deb="$stage/NTKSoundLab-$version-linux-arm64"
mkdir "$deb/DEBIAN"
cat > "$deb/DEBIAN/control" <<CONTROL
Package: ntk-soundlab-studio
Version: $version-1
Architecture: arm64
Maintainer: NTK Hub
Section: sound
Depends: ca-certificates, xdg-utils
Recommends: chromium | chromium-browser
Conflicts: omnistream-studio
Replaces: omnistream-studio
Provides: omnistream-studio
Description: NTK Hub audio and karaoke studio
 Local audio editing, lyrics and video export using an installed browser.
CONTROL
mv "$deb/README.md" "$deb/usr/share/doc/ntk-soundlab-studio/README.md"
deb_file="ntk-soundlab_${version}-1_arm64.deb"
dpkg-deb --root-owner-group --build "$deb" "$stage/$deb_file"
install -m644 "$stage/$deb_file" "$output/$deb_file"

rpm="$stage/rpm"
mkdir -p "$rpm"
cat > "$stage/soundlab.spec" <<SPEC
Name: ntk-soundlab-studio
Version: $version
Release: 1
Summary: NTK Hub audio and karaoke studio
License: MIT
URL: https://github.com/appdevmanwill/NTK-SoundLab-Studio
Requires: ca-certificates, xdg-utils
BuildArch: x86_64
%global debug_package %{nil}
%description
Local audio editing, lyrics and video export using an installed browser.
%install
mkdir -p %{buildroot}/usr
cp -a "$stage/NTKSoundLab-$version-linux-amd64/usr/." %{buildroot}/usr/
%files
%{_bindir}/ntk-soundlab-studio
%{_datadir}/applications/$icon.desktop
%{_datadir}/icons/hicolor/192x192/apps/$icon.png
%license %{_datadir}/doc/ntk-soundlab-studio/copyright
SPEC
rpmbuild -bb --define "_topdir $rpm" --define "_dbpath $rpm/db" "$stage/soundlab.spec"
rpm_file="ntk-soundlab-studio-$version-1.x86_64.rpm"
install -m644 "$rpm/RPMS/x86_64/$rpm_file" "$output/$rpm_file"

if [ "$mode" = flatpak ]; then
    flatpak_dir="$stage/flatpak"
    mkdir "$flatpak_dir"
    cp "$here/$icon.yml" "$here/$icon.desktop" "$here/$icon.metainfo.xml" "$flatpak_dir/"
    install -m755 "$binaries/soundlab-amd64" "$flatpak_dir/ntk-soundlab-studio"
    cp "$root/extension/icons/icon-128.png" "$flatpak_dir/$icon.png"
    flatpak-builder --user --disable-download --state-dir="$stage/state" --repo="$stage/repo" "$stage/build" "$flatpak_dir/$icon.yml"
    flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo "$stage/repo" "$output/NTKSoundLab-$version-x86_64.flatpak" "$icon"
fi
