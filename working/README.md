# Browser app

This directory is the shared frontend used by the web, Windows, Linux and Android versions of SoundLab. It uses JavaScript modules, Web Audio, Canvas and IndexedDB.

## Run locally

From this directory, run the bundled static server.

```sh
python helper/local_server.py --port 5000
```

Open `http://127.0.0.1:5000`. On Windows, `Start-Static-PWA.bat` at the repository root starts the same server. The launcher also has a PHP fallback.

Keep the address and port consistent when working with saved data. Browser storage belongs to the origin, so another port opens a separate library.

## Files worth knowing

| File | Purpose |
| --- | --- |
| `index.html` | Studio interface |
| `js/app.js` | Screen actions and editor coordination |
| `js/transcribe-studio.js` | Transcript editor and local history |
| `js/transcribe-engine.js` | Bounded decoding and recognition requests |
| `js/transcript-store.js` | Transcript persistence and revision checks |
| `js/stem-engine.js` | Local helper and browser stem processing |
| `js/offline-model.js` | Model verification and import |
| `js/storage.js`, `js/vault-db.js` | Library records, media and settings |
| `js/video-generator.js` | Karaoke preview and video export |
| `sw.js` | Web app caching |
| `helper/local_server.py` | Loopback server with an asset allowlist |

The build script in `../desktop/build.ps1` copies the frontend files listed by its allowlist and writes `assets-manifest.json`. Android reads that manifest when creating its bundle. Regenerate the staged assets after a frontend change.

```powershell
powershell -File desktop/build.ps1 -StageOnly
```

Run that command from the repository root.

## Optional Python helper

The helper adds site extraction and local stem processing. Install it in a virtual environment if you need those features.

```sh
python -m venv .venv
```

Activate the environment with `.venv\Scripts\activate` on Windows, or `source .venv/bin/activate` on Linux, then install the requirements and start the helper.

```sh
python -m pip install -r helper/requirements.txt
python helper/soundlab_helper.py --serve --port 8899
```

Open `http://127.0.0.1:8899` to use its authenticated local page. The packaged desktop app can connect to supported helper features.

The base requirements include yt-dlp and cryptography. Native HTDemucs processing additionally needs compatible PyTorch and Demucs installations. FFmpeg is needed for helper operations that perform conversion. Hardware and package compatibility should be checked on the machine running them.

The helper stores cookies in the current user's private SoundLab configuration directory. It imports an earlier cookie file when needed. Cookie management is available through the local helper page.

## Checks

From the repository root, run the helper tests.

```sh
python -m unittest discover -s working/helper -p test_soundlab.py
```

Desktop checks are run from `desktop/` with `go test ./...`. Backend checks are described in the [Laravel guide](../laravel/README.md).

The app can run with AI disabled. Use simulated provider responses in workflow tests and an owner-approved recording and account when testing recognition accuracy.

## Hosting

Publish the browser assets over HTTPS. The released static ZIP contains the staged assets selected for the app. The Python helper and Laravel backend need their own runtime environments.

For PHP hosting, use the [deployment guide](../DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md). For the optional offline weights, use the [model guide](../SOFTWARE/OFFLINE_MODELS/README.md).
