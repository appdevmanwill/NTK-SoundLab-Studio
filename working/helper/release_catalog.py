"""Generate the public download table and SHA-256 manifest from one set of files."""

import argparse
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
START = '<!-- release-downloads:start -->'
END = '<!-- release-downloads:end -->'
DOWNLOADS = (
    ('Windows x64', 'Portable EXE', 'SOFTWARE/PORTABLE/WINDOWS/NTKSoundLab-Portable-{version}.exe'),
    ('Windows x64', 'Setup installer', 'SOFTWARE/INSTALLERS/WINDOWS/NTKSoundLab-Setup-{version}.exe'),
    ('Linux x64', 'AppImage', 'SOFTWARE/LINUX/NTKSoundLab-{version}-x86_64.AppImage'),
    ('Linux x64', 'Debian package', 'SOFTWARE/LINUX/ntk-soundlab_{version}-1_amd64.deb'),
    ('Android 10+', 'APK', 'SOFTWARE/ANDROID/NTKSoundLab-{version}.apk'),
    ('Web', 'Static PWA ZIP', 'SOFTWARE/WEB/NTKSoundLab-Static-{version}.zip'),
    ('PHP hosting', 'Laravel hosting ZIP', 'DEPLOY_MANUAL/NTK_SoundLab_Studio_AlwaysData-{version}.zip'),
)
PLAY_BUNDLE = ('Google Play', 'Signed AAB', 'SOFTWARE/ANDROID/NTKSoundLab-{version}.aab')
EXTENSION_ZIP = ('Chrome / Edge', 'Browser Grabber ZIP', 'SOFTWARE/EXTENSION/NTKSoundLab-Browser-Grabber-{version}.zip')
RELEASE_BASE_URL = 'https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/download/v{version}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    parser.add_argument('--desktop-version', help='Desktop-only update version; other platforms keep the base version.')
    parser.add_argument('--grabber-version', help='Use separate browser ZIPs from this release version.')
    parser.add_argument('--linux-extras-version', help='Include the RPM, ARM64 DEB and portable Linux archives.')
    parser.add_argument('--flatpak', action='store_true', help='Include a Flatpak bundle from the Linux extras version.')
    parser.add_argument('--mobile-preview', action='store_true', help='Include the unsigned Firefox Android test package.')
    parser.add_argument('--check', action='store_true', help='Fail if the catalog does not match the files.')
    parser.add_argument('--download-base-url', default=RELEASE_BASE_URL, help='Release asset URL prefix. Supports {version}.')
    args = parser.parse_args()
    if not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}\.\d+', args.version):
        parser.error('Use a SoundLab release version such as 2026.11.11.1.')
    for version in (args.desktop_version, args.grabber_version, args.linux_extras_version):
        if version and not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}\.\d+', version):
            parser.error('Use SoundLab release versions for the optional packages.')
    if args.flatpak and not args.linux_extras_version:
        parser.error('--flatpak requires --linux-extras-version.')
    if args.mobile_preview and not args.grabber_version:
        parser.error('--mobile-preview requires --grabber-version.')

    table = ['| Platform | Download |', '| --- | --- |']
    checksums = []
    downloads = list(DOWNLOADS)
    grabber_version = args.grabber_version or args.desktop_version
    release_version = args.grabber_version or args.linux_extras_version or args.desktop_version or args.version
    for optional in (EXTENSION_ZIP, PLAY_BUNDLE):
        if optional == EXTENSION_ZIP and grabber_version:
            continue
        if (ROOT / optional[2].format(version=args.version)).is_file():
            downloads.append(optional)
    if args.linux_extras_version:
        version = args.linux_extras_version
        downloads.extend([
            ('Linux x64', 'Fedora-style RPM', f'SOFTWARE/LINUX/ntk-soundlab-studio-{version}-1.x86_64.rpm'),
            ('Linux ARM64', 'Debian package', f'SOFTWARE/LINUX/ntk-soundlab_{version}-1_arm64.deb'),
            ('Linux x64', 'Portable archive', f'SOFTWARE/LINUX/NTKSoundLab-{version}-linux-amd64.tar.gz'),
            ('Linux ARM64', 'Portable archive', f'SOFTWARE/LINUX/NTKSoundLab-{version}-linux-arm64.tar.gz'),
        ])
        if args.flatpak:
            downloads.append(('Linux x64', 'Flatpak preview', f'SOFTWARE/LINUX/NTKSoundLab-{version}-x86_64.flatpak'))
    if grabber_version:
        for browser in ('Chrome', 'Firefox', 'Opera', 'Edge'):
            downloads.append((browser, 'Media Grabber ZIP', f'SOFTWARE/EXTENSION/{browser.upper()}/NTKSoundLab-Browser-Grabber-{browser}-{grabber_version}.zip'))
    if args.mobile_preview:
        downloads.append(('Firefox Android', 'Unsigned extension test ZIP', f'SOFTWARE/EXTENSION/FIREFOX-ANDROID/NTKSoundLab-Browser-Grabber-Firefox-Android-{grabber_version}.zip'))
    for platform, kind, template in downloads:
        file_version = args.desktop_version if args.desktop_version and platform in ('Windows x64', 'Linux x64') else args.version
        relative = template.format(version=file_version)
        file = ROOT / relative
        if not file.is_file() or not file.stat().st_size:
            parser.error(f'Missing release file {relative}')
        with file.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        url = args.download_base_url.format(version=release_version).rstrip('/') + '/' + file.name
        table.append(f'| {platform} | [{kind}]({url}) |')
        checksums.append(f'{digest}  {file.name}')

    readme = ROOT / 'README.md'
    manifest = ROOT / 'SOFTWARE' / 'SHA256SUMS.txt'
    text = readme.read_text(encoding='utf-8')
    head, start, rest = text.partition(START)
    _, end, tail = rest.partition(END)
    if not start or not end:
        parser.error('README download table markers are missing.')
    rendered = head + start + '\n\n' + '\n'.join(table) + '\n\n' + end + tail
    sums = '\n'.join(checksums) + '\n'
    if args.check:
        if rendered != text or not manifest.is_file() or manifest.read_text(encoding='utf-8') != sums:
            parser.error('The release catalog is out of date.')
    else:
        readme.write_text(rendered, encoding='utf-8')
        manifest.write_text(sums, encoding='utf-8')
    print(f'Verified {len(checksums)} release digests for {args.version}.')


if __name__ == '__main__':
    main()
