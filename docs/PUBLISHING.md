# Publish SoundLab

This page is for the NTK Hub publisher. Use the packages from the verified release and keep publisher accounts, signing keys and credentials private.

## Browser add-ons

| Destination | Upload and next step |
| --- | --- |
| **Chrome Web Store** | Upload the Chrome ZIP from the owner’s developer dashboard. Add screenshots, a support link, privacy disclosures and reasons for each permission. Registration requires a one-time fee for a new developer account. [Registration](https://developer.chrome.com/docs/webstore/register) |
| **Microsoft Edge Add-ons** | Upload the Edge ZIP in Partner Center, complete privacy and listing details, and submit it for certification. Microsoft documents free extension developer registration. [Publishing guide](https://learn.microsoft.com/en-us/microsoft-edge/extensions/publish/publish-extension), [Registration](https://learn.microsoft.com/en-us/microsoft-edge/extensions-chromium/publish/create-dev-account) |
| **Firefox Add-ons** | Upload the Firefox ZIP in the Add-on Developer Hub. Choose a public listing or request an unlisted signed XPI for GitHub distribution. Keep the existing add-on ID for updates. [Mozilla signing](https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/) |
| **Opera Add-ons** | Use the Opera ZIP as the submission candidate and confirm the current store requirements in the publisher dashboard. Test detection, actual downloads and recording in Opera before submission. |
| **Brave and Vivaldi** | Reuse the Chromium package after compatibility tests. If a Chrome Web Store listing is approved, link users to that install route. [Brave](https://support.brave.app/hc/en-us/articles/360017909112-How-can-I-add-extensions-to-Brave), [Vivaldi](https://help.vivaldi.com/desktop/appearance-customization/extensions/) |
| **Safari** | Prototype macOS first. Safari on iOS lacks the webRequest API that the current grabber uses to detect streams. An iPhone/iPad version needs a different capture flow. Test each supported operation on Apple devices before packaging. [Apple compatibility guide](https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility) |

Describe the actual product and its permission use. Clip editing, model inference and conversions run locally. Capture observes media responses and records a surface only after the browser's selection prompt. Review your listing against the store's media policies and demonstrate it with recordings you own or have permission to use. [Chrome Store prohibited products](https://developer.chrome.com/docs/webstore/program-policies/malicious-and-prohibited/)

## Google Play

Create the SoundLab listing with the owner’s Play developer account. Start on the **Internal testing** track and upload the **signed AAB** for `com.ntkhub.soundlabstudio`. For later updates keep that ID, increase the version code, and sign the new AAB with the accepted upload key. Google Play App Signing manages the key used to sign APKs delivered to users. Keep the private upload key off GitHub. [Play App Signing](https://developer.android.com/studio/publish/app-signing)

Prepare phone screenshots and check privacy policy, Data safety, target API, app access and content rating. Test installs and exports on a physical phone. New personal accounts created after 13 November 2023 generally need a closed test with at least **12 testers opted in continuously for 14 days** before applying for production access. [Testing requirement](https://support.google.com/googleplay/android-developer/answer/14151465)

The signed preview bundle targets Android API 36, which matches the documented minimum for ordinary new apps and updates as of November 2026. Confirm the upload checks in Play Console. [Target API requirement](https://developer.android.com/google/play/requirements/target-sdk)

## Linux distribution

Use GitHub Releases for AppImages, DEBs, RPMs and portable archives, with checksums and install instructions. Run installation, first launch, import, export and uninstall on representative Linux desktops before marking them supported. Verify ARM packages on ARM hardware and test against the browser users can install on their distribution.

For **Flathub**, prepare the source build manifest and app metadata, verify the app identity and test the sandbox, browser portal and writable storage. A GitHub Flatpak bundle can be used for testing. Follow Flathub's submission and disclosure requirements for reviewed, AI-assisted material. [Flathub submission](https://docs.flathub.org/docs/for-app-authors/submission), [Requirements](https://docs.flathub.org/docs/for-app-authors/requirements)

For an official distribution repository, follow that distribution's package review and maintenance process. Start with downloadable packages and verify install or update before pursuing a distribution listing.
