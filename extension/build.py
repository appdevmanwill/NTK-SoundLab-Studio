"""Package the shared Media Grabber for Chrome, Edge, Opera and Firefox."""

import argparse
import json
import re
from pathlib import Path
from shutil import copyfile
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
SHARED = ROOT.parent / 'working'
STUDIO_MODULES = (
    'ai-policy', 'network-policy', 'vault-db', 'audio-converter',
    'audio-fx', 'mp3-encoder', 'id3-writer', 'stem-engine', 'stem-mixer', 'offline-model',
)


def package_files():
    for path in ROOT.iterdir():
        if path.is_file() and path.suffix in ('.js', '.mjs', '.html', '.css', '.md'):
            yield path, path.name
    for folder in ('icons', 'lib'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file():
                yield path, path.relative_to(ROOT).as_posix()
    for name in STUDIO_MODULES:
        path = f'js/{name}.js'
        yield SHARED / path, path
    for folder in ('lib/demucs-web', 'lib/onnxruntime/1.20.1'):
        for path in (SHARED / folder).rglob('*'):
            if path.is_file():
                yield path, path.relative_to(SHARED).as_posix()


def manifest_for(browser):
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    if browser.startswith('Firefox'):
        manifest['background'] = {'scripts': ['background.js'], 'type': 'module'}
        manifest['browser_specific_settings'] = {
            'gecko': {
                'id': 'soundlab-grabber@ntkhub',
                'strict_min_version': '142.0',
                'data_collection_permissions': {'required': ['none']},
            }
        }
        if browser == 'Firefox-Android':
            manifest['browser_specific_settings']['gecko_android'] = {'strict_min_version': '142.0'}
    return json.dumps(manifest, indent=2) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    parser.add_argument('--stage', type=Path, help='Write an unpacked test folder instead of ZIPs.')
    parser.add_argument('--browser', choices=('Chrome', 'Edge', 'Opera', 'Firefox', 'Firefox-Android'), default='Chrome')
    parser.add_argument('--mobile-preview', action='store_true', help='Also package the Firefox Android test candidate.')
    args = parser.parse_args()
    if not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}\.\d+', args.version):
        parser.error('Use a SoundLab release version.')
    files = sorted(package_files(), key=lambda item: item[1])
    if args.stage:
        args.stage.mkdir(parents=True, exist_ok=False)
        (args.stage / 'manifest.json').write_text(manifest_for(args.browser), encoding='utf-8')
        for source, relative in files:
            destination = args.stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            copyfile(source, destination)
        return
    browsers = ['Chrome', 'Edge', 'Opera', 'Firefox']
    if args.mobile_preview:
        browsers.append('Firefox-Android')
    for browser in browsers:
        folder = ROOT.parent / 'SOFTWARE' / 'EXTENSION' / browser.upper()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f'NTKSoundLab-Browser-Grabber-{browser}-{args.version}.zip'
        with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', manifest_for(browser))
            for source, relative in files:
                archive.write(source, relative)
        print(target.relative_to(ROOT.parent))


if __name__ == '__main__':
    main()
