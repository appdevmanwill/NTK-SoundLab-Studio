# NTK SoundLab Media Grabber (Chrome / Edge Extension)

Captures playing audio and video streams inside Chrome or Microsoft Edge via Manifest V3 `chrome.webRequest` response detection and DOM resource scanning, and lets you either save them cleanly or send them directly into **NTK SoundLab Studio** (Live Web, Desktop, or Localhost).

## Why a Browser Extension?

When websites such as Audiomack or dynamic HTML5 players use signed playback sessions (`OAuth` tokens, per-session headers, or in-memory `new Audio()` players), standalone servers cannot read those browser-tab streams directly. Running this extension in your browser observes standard unencrypted `audio/*` and `video/*` streams emitted as you play a track and hands the media straight to NTK SoundLab Studio's stem separator, trimmer, FX rack, transcriber, and karaoke studio.

## Install Unpacked in Chrome or Edge (3 Steps)

1. Download and extract `NTKSoundLab-Browser-Grabber-<version>.zip` (or point directly to this `extension/` folder).
2. Open `chrome://extensions` in Chrome (or `edge://extensions` in Microsoft Edge) and enable **Developer mode**.
3. Click **Load unpacked** and select the extracted folder containing `manifest.json`.

## Usage

1. Open any media page (for example Audiomack, SoundCloud, Flow Music, ACE Music, etc.) and click **Play**.
2. Click the **NTK SoundLab Media Grabber** toolbar icon.
3. Choose **⚡ Send to SoundLab** (live Firebase Web, Desktop `127.0.0.1:47831`, or Localhost `127.0.0.1:8000`) or **⬇ Save**.
