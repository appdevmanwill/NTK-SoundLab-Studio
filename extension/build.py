"""Package the shared Media Grabber for Chrome, Edge, Opera and Firefox."""

import argparse
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    args = parser.parse_args()
    if not re.fullmatch(r'\d{4}\.\d{1,2}\.\d{1,2}\.\d+', args.version):
        parser.error('Use a SoundLab release version.')
    files = [file for file in ROOT.iterdir() if file.is_file() and file.suffix in ('.js', '.mjs', '.html', '.css', '.md')]
    for folder in ('icons', 'lib'):
        files.extend(file for file in (ROOT / folder).rglob('*') if file.is_file())
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    for browser in ('Chrome', 'Edge', 'Opera', 'Firefox'):
        browser_manifest = json.loads(json.dumps(manifest))
        if browser == 'Firefox':
            browser_manifest['background'] = {'scripts': ['background.js'], 'type': 'module'}
            browser_manifest['browser_specific_settings'] = {
                'gecko': {
                    'id': 'soundlab-grabber@ntkhub',
                    'strict_min_version': '142.0',
                    'data_collection_permissions': {'required': ['none']},
                }
            }
        folder = ROOT.parent / 'SOFTWARE' / 'EXTENSION' / browser.upper()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f'NTKSoundLab-Browser-Grabber-{browser}-{args.version}.zip'
        with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(browser_manifest, indent=2) + '\n')
            for file in sorted(files):
                archive.write(file, file.relative_to(ROOT).as_posix())
        print(target.relative_to(ROOT.parent))


if __name__ == '__main__':
    main()
