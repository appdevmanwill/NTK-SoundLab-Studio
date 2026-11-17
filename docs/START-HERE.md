# Start using SoundLab

SoundLab is an audio and karaoke editor from NTK Hub. Start with your own short recording. You can trim it and save a copy without an account or an AI key.

| What you want to do | Where to start |
| --- | --- |
| Try the editor | [Open SoundLab in your browser](https://studio-5090403114-fc98b.web.app/) |
| Edit without relying on a hosted site | [Install the Windows, Linux or Android app](../SOFTWARE/README-LATEST.md) |
| Save supported media from a page | [Install the Media Grabber extension](../extension/README.md) |
| Put a copy of SoundLab on your own website | [Choose a hosting option](HOSTING.md) |

## Save your first clip

1. Open SoundLab and choose **Import Video or Audio**. On Android, tap **Import audio or video**.
2. Pick a short MP3 or WAV you own. Find its card and select **Trim & FX**.
3. Play the clip and choose a start and end time. Preview the result, then save it as WAV or MP3.
4. Open your Downloads folder and play the exported file to check it. Your input file stays intact.

## What to try next

- **Make a backing track.** Use **Offline Storage** to import the verified stem model. Choose two stems to get vocals and instrumental, then play or save either track. Four stems give you separate vocals, drums, bass and other instruments. [Model setup](../SOFTWARE/OFFLINE_MODELS/README.md)
- **Make a lyric video.** Open **Video Studio**, add your lyrics, and preview their timing before exporting. Try a short clip at a lower resolution first.
- **Make subtitles.** Open **Transcribe**, choose your recording and set up your own Groq key privately. SoundLab asks before sending audio to Groq. Review the text and timing before saving your SRT.
- **Save audio or video from a page.** Open the grabber while the media plays. Choose the complete item and select the format. For a visible storyboard preview, use **Record playback with sound** and select that tab in the browser's picker. [Browser extension guide](../extension/README.md)

## If you get stuck

| What you see | What to try |
| --- | --- |
| I downloaded a source code ZIP | Go back to the release downloads and pick your installer, APK, or browser ZIP. |
| Windows shows an unknown publisher | The preview EXE is unsigned. Check that it came from the official GitHub release and compare the checksum. |
| My Android phone cannot open the AAB | Download the APK. The signed AAB is for the app publisher to upload to Google Play. |
| Firefox removed the extension when it restarted | This is a temporary installation. Follow the Firefox steps again until a signed add-on is available. |
| The grabber only sees audio | The page may use separate audio or a storyboard instead of a finished video. Use the site's export option, or record visible playback with tab sound where supported. |
| My library is empty after I moved to another browser or site | Go back to the original browser profile and address. Save the recordings and export session metadata before moving. |

Keep copies of important recordings and exports outside the browser. A session export includes project metadata and lyrics. Keep the audio and video files alongside it. Browser sites and profiles each have their own local storage.

If you report a problem, include your operating system, browser and SoundLab version, the steps you took and the error text. Leave out provider keys, cookies, private recordings and signed media links. [Report a problem](https://github.com/appdevmanwill/NTK-SoundLab-Studio/issues/new)
