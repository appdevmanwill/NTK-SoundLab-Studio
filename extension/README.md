# NTK SoundLab Media Grabber

Save audio and video playing in your browser, or send a complete media file to SoundLab for editing. Built by NTK for NTK Hub.

## Install

Use the ZIP named for your browser and extract it into a folder you intend to keep.

| Browser | Install the preview |
| --- | --- |
| Chrome | Open `chrome://extensions`, enable Developer mode, choose Load unpacked and select the extracted folder. |
| Microsoft Edge | Open `edge://extensions`, enable Developer mode, choose Load unpacked and select the extracted folder. |
| Opera | Open `opera://extensions`, enable Developer mode, choose Load unpacked and select the extracted folder. Enable access to the media website if Opera asks. |
| Firefox 142+ | Open `about:debugging#/runtime/this-firefox`, choose Load Temporary Add-on and select `manifest.json` in the Firefox folder. Firefox removes temporary add-ons when it restarts. |

The Firefox preview is unsigned. Permanent Firefox installation requires Mozilla signing. Browser-store publication is pending.

## Save a recording or video

1. Play the media on its original website. Select the highest available quality in that website's player.
2. Open SoundLab Media Grabber from your browser toolbar.
3. Choose the complete audio, video or HLS playlist entry.
4. Choose Original, MP3 320k, WAV 24-bit or Save video. The download opens in its own tab.
5. Select Save file and keep that tab open until the file is saved.

The export page shows the source video dimensions, audio sample rate and channel count when available. It has a progress indicator and Cancel button. Temporary converted files are stored locally while saving.

| Format | What you receive |
| --- | --- |
| Original | The complete source file with its existing encoding and quality. |
| MP3 320k | MP3 encoded at 320 kbps, mono or stereo. MP3 supports sample rates up to 48 kHz. |
| WAV 24-bit | Uncompressed 24-bit PCM using the source audio sample rate and channel count. |
| Video | MP4 with the selected source video and audio copied without re-encoding when their codecs fit MP4. |

WAV can retain high-resolution audio when the source provides it. A compressed stream converted to WAV still contains the source's original limitations. Conversion cannot recover missing audio detail or create higher video resolution.

HLS exports choose the largest exposed video rendition and compatible audio. Some sites supply video and audio in separate URLs without a common playlist. A video-only capture can therefore be silent. DASH manifests, live broadcasts, encrypted/DRM playback and individual media segments are not supported by the file exporter. A website's access controls, expiring links, codecs and browser permissions also affect what can be saved. Support varies by website.

## When the player is a storyboard or animated page

An Atlabs storyboard, for example, can show images and captions in time with separate audio. There may be no finished video file for the grabber to find. The site's own Export option is the best route to a rendered final video when available.

To save visible playback, choose **Record playback with sound** in the grabber. Pause the source at the beginning, select that browser tab, and enable **Share tab audio** in the browser's picker. Press **Start recording**, return to the source during the five-second countdown, and play it. Return to the recording tab and choose **Stop & save** when it ends. Fullscreen playback keeps the rest of the page out of the recording.

The recorder saves MP4 when the browser supports H.264/AAC recording, otherwise WebM. This re-encodes what is visible at the captured tab's resolution; it is not a source-quality download. The recorder refuses to start without shared audio unless you explicitly allow silence. Firefox may not provide screen-capture audio; use Chrome, Edge or Opera for tab recording with sound. Recordings stop at one hour or 2 GB. Keep the recorder page open until saving finishes.

## Send to SoundLab

Select a complete media file, choose your SoundLab website or desktop destination, and press Send to SoundLab. For video, this action is labelled **Edit audio in SoundLab** because the studio imports its audio for editing. Use **Save video** to keep the picture and sound. Direct transfers support files up to 150 MB. Save an HLS stream first, then import the resulting file into SoundLab.

The desktop app uses a dedicated Chrome profile. Install the extension in the browser profile you use to play the source media. When the grabber and desktop window use different profiles, save the file and import it through SoundLab's Import Video or Audio button.

## Permissions and privacy

The grabber watches media response headers and inspects media elements in tabs where access is allowed. It keeps captured URLs in session storage, which is cleared when the browser session ends. Signed media URLs may contain temporary playback tokens. Clear a tab's capture list when you finish.

Downloads go directly from the source site to your computer. MP3, WAV and video processing runs locally. Recording uses the browser's capture picker each time and stays local. Converted files and recordings use temporary browser storage; interrupted browser sessions may leave temporary files until the extension's data is cleared. Sending to SoundLab happens only when you choose that action. This extension has no analytics or telemetry.

## Development

`python extension/build.py 2026.11.16.4` creates four packages in `SOFTWARE/EXTENSION`. The Chromium browsers share the same runtime. Firefox uses a module background script and its own manifest identity.

Media container handling uses the bundled Mediabunny 1.65.0 module under MPL-2.0. MP3 encoding uses the existing lamejs library. License and source notices are included in `lib/`.
