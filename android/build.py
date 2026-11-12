"""Offline Android SDK build, using the canonical shared frontend allowlist.

No Gradle/Maven downloads. Signing key lives outside source/releases; its random
password is protected with Windows DPAPI for this Windows user, never printed.
"""
import argparse, ctypes, hashlib, json, os, secrets, shutil, subprocess, tempfile, zipfile
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SIGNING_ALIAS = 'soundlab'
ANDROID_XML = '{http://schemas.android.com/apk/res/android}'
BUNDLETOOL_VERSION = '1.18.3'
BUNDLETOOL_SHA256 = 'a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29'

def run(args, **kwargs):
    result = subprocess.run([str(x) for x in args], check=True, capture_output=True, text=True, **kwargs)
    if result.stdout.strip(): print(result.stdout.strip())
    if result.stderr.strip(): print(result.stderr.strip())
    return result

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_byte))]

def protect(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    crypt = ctypes.windll.crypt32
    ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)) if decrypt else crypt.CryptProtectData(ctypes.byref(source), 'NTK Android signing', None, None, None, 0, ctypes.byref(output))
    if not ok: raise ctypes.WinError()
    try: return ctypes.string_at(output.data, output.size)
    finally: ctypes.windll.kernel32.LocalFree(output.data)

def signing_credentials(java, env, initialize):
    keydir = Path(os.environ['LOCALAPPDATA']).resolve() / 'NTKSoundLabStudio' / 'android-signing'
    keydir.parent.mkdir(parents=True, exist_ok=True)
    if keydir.resolve() != keydir:
        raise SystemExit('SoundLab signing directory must be inside the local Windows profile.')
    key = keydir / 'soundlab-release.p12'
    password_file = keydir / 'password.dpapi'
    if not keydir.exists():
        if not initialize:
            raise SystemExit('Restore the SoundLab signing files, or pass --init-signing for a new app identity.')
        with tempfile.TemporaryDirectory(prefix='android-signing-', dir=keydir.parent) as temporary:
            pending = Path(temporary).resolve()
            if pending.parent != keydir.parent:
                raise SystemExit('Signing stage must be inside the SoundLab profile.')
            password = secrets.token_urlsafe(40)
            (pending / password_file.name).write_bytes(protect(password.encode()))
            run([
                java / 'keytool.exe', '-genkeypair', '-keystore', pending / key.name,
                '-storetype', 'PKCS12', '-storepass:env', 'NTK_ANDROID_STOREPASS',
                '-keypass:env', 'NTK_ANDROID_STOREPASS', '-alias', SIGNING_ALIAS,
                '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10000',
                '-dname', 'CN=NTK Hub SoundLab Studio, O=NTK Hub, C=NG',
            ], env={**env, 'NTK_ANDROID_STOREPASS': password})
            try:
                pending.rename(keydir)
            except FileExistsError:
                # A concurrent build published its complete signing pair first.
                pass
    if not key.is_file() or not password_file.is_file():
        raise SystemExit('SoundLab signing state is incomplete. Restore its matching keystore and protected password.')
    return key, protect(password_file.read_bytes(), True).decode()

def build_bundle(build, compiled, app_manifest, platform, tools, java, tool, key, env, version):
    with tool.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != BUNDLETOOL_SHA256:
            raise SystemExit('Bundletool does not match the pinned official release digest.')
    proto = build / 'protobuf.apk'
    run([
        tools / 'aapt2.exe', 'link', '--proto-format', '-o', proto,
        '--manifest', app_manifest, '-I', platform, '-A', build / 'assets',
        '--min-sdk-version', '29', '--target-sdk-version', '36',
        '--auto-add-overlay', compiled,
    ])
    module = build / 'base.zip'
    with zipfile.ZipFile(proto) as source, zipfile.ZipFile(module, 'w', zipfile.ZIP_DEFLATED) as destination:
        for name in source.namelist():
            if name.endswith('/'):
                continue
            target = 'manifest/AndroidManifest.xml' if name == 'AndroidManifest.xml' else name
            destination.writestr(target, source.read(name))
        for dex in (build / 'dex').glob('*.dex'):
            destination.write(dex, 'dex/' + dex.name)
    output = build / f'NTKSoundLab-{version}-release.aab'
    run([java / 'java.exe', '-jar', tool, 'build-bundle', '--modules=' + str(module), '--output=' + str(output)])
    run([
        java / 'jarsigner.exe', '-keystore', key, '-storetype', 'PKCS12',
        '-storepass:env', 'NTK_ANDROID_STOREPASS', '-keypass:env', 'NTK_ANDROID_STOREPASS',
        '-digestalg', 'SHA-256', '-sigalg', 'SHA256withRSA', output, SIGNING_ALIAS,
    ], env=env)
    run([
        java / 'jarsigner.exe', '-verify', '-strict', '-keystore', key,
        '-storepass:env', 'NTK_ANDROID_STOREPASS', output,
    ], env=env)
    run([java / 'java.exe', '-jar', tool, 'validate', '--bundle=' + str(output)])
    certificate = build / 'NTKSoundLab-upload-certificate.pem'
    run([
        java / 'keytool.exe', '-exportcert', '-rfc', '-keystore', key,
        '-storepass:env', 'NTK_ANDROID_STOREPASS', '-alias', SIGNING_ALIAS,
        '-file', certificate,
    ], env=env)
    return {
        'aab': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'bytes': output.stat().st_size, 'certificate': str(certificate),
        'bundletool': BUNDLETOOL_VERSION, 'bundletoolSha256': BUNDLETOOL_SHA256,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--init-signing', action='store_true', help='Create the signing key for a new SoundLab identity.')
    parser.add_argument('--bundle', action='store_true', help='Also build and validate a signed release AAB for Google Play.')
    parser.add_argument('--bundletool', type=Path, help='Path to the pinned official bundletool JAR.')
    args=parser.parse_args()
    if args.bundle and args.debug:
        parser.error('Build the Play bundle in release mode.')
    sdk=Path(os.environ.get('ANDROID_SDK_ROOT', str(Path(os.environ['LOCALAPPDATA'])/'Android'/'Sdk')))
    java=Path(os.environ.get('JAVA_HOME', r'C:\Program Files\Eclipse Adoptium\jdk-21.0.13.9-hotspot'))/'bin'
    tools=sdk/'build-tools'/'36.1.0'; platform=sdk/'platforms'/'android-36.1'/'android.jar'
    for required in [tools/'aapt2.exe',tools/'d8.bat',tools/'apksigner.bat',platform,java/'javac.exe']:
        if not required.is_file(): raise SystemExit(f'Required installed tool missing: {required}')
    bundletool = args.bundletool or Path(os.environ['LOCALAPPDATA']) / 'NTKSoundLabStudio' / 'build-tools' / f'bundletool-all-{BUNDLETOOL_VERSION}.jar'
    if args.bundle:
        for required in (bundletool, java / 'java.exe', java / 'jarsigner.exe'):
            if not required.is_file():
                raise SystemExit(f'Required bundle build tool missing: {required}')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    mode='debug' if args.debug else 'release';build=HERE/'build'/f'{mode}-{stamp}';build.mkdir(parents=True)
    assets=build/'assets'/'www';assets.mkdir(parents=True)
    manifest=json.loads((ROOT/'desktop'/'assets-manifest.json').read_text(encoding='utf-8-sig'))
    included=[]
    for item in manifest:
        rel=item['path'];source=ROOT/'working'/rel
        if Path(rel).is_absolute() or '..' in Path(rel).parts or not source.is_file():raise SystemExit(f'Unsafe or missing asset: {rel}')
        target=assets/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        included.append({'path':rel,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
    shutil.copytree(HERE/'web',assets/'native')
    html=(assets/'index.html').read_text(encoding='utf-8')
    # Native bundle needs no Google Font network request on first launch.
    html='\n'.join(line for line in html.splitlines() if 'fonts.googleapis.com' not in line and 'fonts.gstatic.com' not in line)
    html=html.replace('<head>','<head>\n  <script src="native/android.js"></script>',1).replace('</head>','  <link rel="stylesheet" href="native/android.css" />\n</head>',1)
    (assets/'index.html').write_text(html,encoding='utf-8')
    manifest_text=(HERE/'AndroidManifest.xml').read_text(encoding='utf-8')
    identity = ElementTree.fromstring(manifest_text)
    version = identity.attrib[ANDROID_XML + 'versionName']
    if args.debug:manifest_text=manifest_text.replace('<application ','<application android:debuggable="true" ',1)
    app_manifest=build/'AndroidManifest.xml';app_manifest.write_text(manifest_text,encoding='utf-8')
    compiled=build/'resources.zip';run([tools/'aapt2.exe','compile','--dir',HERE/'res','-o',compiled])
    unsigned=build/'unsigned.apk'
    run([tools/'aapt2.exe','link','-o',unsigned,'--manifest',app_manifest,'-I',platform,'-A',build/'assets','--min-sdk-version','29','--target-sdk-version','36','--auto-add-overlay',compiled])
    classes=build/'classes';classes.mkdir();sources=list((HERE/'src').rglob('*.java'))
    run([java/'javac.exe','-encoding','UTF-8','--release','8','-classpath',platform,'-d',classes,*sources])
    jar=build/'classes.jar';run([java/'jar.exe','--create','--file',jar,'-C',classes,'.'])
    dex=build/'dex';dex.mkdir();env=os.environ.copy();env['JAVA_HOME']=str(java.parent)
    run([tools/'d8.bat','--release','--min-api','29','--lib',platform,'--output',dex,jar],env=env)
    with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as z:
        for f in dex.glob('*.dex'):z.write(f,f.name)
    aligned=build/'aligned.apk';run([tools/'zipalign.exe','-P','16','-f','4',unsigned,aligned])
    key, password = signing_credentials(java, env, args.init_signing)
    output=build/f'NTKSoundLab-{version}-{mode}.apk'
    run([tools/'apksigner.bat','sign','--ks',key,'--ks-key-alias',SIGNING_ALIAS,
         '--ks-pass','env:NTK_ANDROID_STOREPASS','--key-pass','env:NTK_ANDROID_STOREPASS',
         '--out',output,aligned],env={**env, 'NTK_ANDROID_STOREPASS': password})
    verification=run([tools/'apksigner.bat','verify','--verbose','--print-certs',output],env=env).stdout
    run([tools/'zipalign.exe','-c','-P','16','-v','4',output])
    result={'version':version,'applicationId':identity.attrib['package'],'mode':mode,'apk':str(output),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'bytes':output.stat().st_size,'minSdk':29,'targetSdk':36,'assets':included,'signingVerification':verification,'buildHost':'Windows; installed Android SDK36.1.0/platform36.1; JDK21'}
    if args.bundle:
        result['bundle'] = build_bundle(
            build, compiled, app_manifest, platform, tools, java, bundletool, key,
            {**env, 'NTK_ANDROID_STOREPASS': password}, version,
        )
    (build/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (HERE/'build'/f'latest-{mode}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'APK ready: {output}')
    if args.bundle:
        print(f"AAB ready: {result['bundle']['aab']}")

if __name__=='__main__':main()
