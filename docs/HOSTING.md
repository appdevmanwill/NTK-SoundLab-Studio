# Host your own SoundLab

You can use the existing browser app or install SoundLab on your device. Hosting is useful when you want to share a copy at your own web address.

The **browser download** is the simplest option. It serves the editor over HTTPS. Visitors can import, edit and export their own files on their devices. The **Laravel download** includes an optional web server for supported remote links and temporary jobs. Start with the browser download unless you need those server functions.

## Publish the browser editor

Download the **Static PWA ZIP** from the README, then extract it. The folder you publish must contain `index.html` next to `css`, `js` and `lib`. Publish the contents of that folder. It is already built.

| Host | Steps | Free plan considerations |
| --- | --- | --- |
| **Cloudflare Pages** | Create a Pages project with **Direct Upload**, then upload the extracted site folder. Use the generated `pages.dev` address. [Upload guide](https://developers.cloudflare.com/pages/get-started/direct-upload/) | The current 20.7 MiB runtime asset fits the 25 MiB file cap. Leave the optional 180 MB model out of your upload. [Limits](https://developers.cloudflare.com/pages/platform/limits/) |
| **Firebase Hosting** | Select your own Firebase project, install the Firebase CLI, run `firebase init hosting` and choose an extracted site folder as the public folder. Keep your existing index and choose **No** for the single-page rewrite. Run `firebase deploy --only hosting`. [Firebase quickstart](https://firebase.google.com/docs/hosting/quickstart) | Spark supplies 10 GB of monthly Hosting transfer. Check the dashboard if your site stops loading. [Hosting limits](https://firebase.google.com/docs/hosting/usage-quotas-pricing) |
| **GitHub Pages** | Put the extracted files on a branch in a public repository and add an empty file named `.nojekyll` next to `index.html`. Under **Settings → Pages**, select the branch and its root folder. Open the Pages URL shown in settings. [Publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) | Test the app at its repository subdirectory address. GitHub restricts use for commercial SaaS and commercial transactions. [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) |
| **Netlify** | Use **Add new project → Deploy manually**, then drag the extracted site folder into the upload area. Open its generated URL. [Manual deploys](https://docs.netlify.com/deploy/create-deploys/) | The current Free plan has 300 monthly credits across metered uses. [Free plan](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans/) |
| **Vercel** | Import a repository containing the extracted site files. Choose **Other** for the framework. Use the directory containing `index.html` and leave build/install commands disabled. [Project settings](https://vercel.com/docs/project-configuration) | Use this route for the browser files. The platform's fair-use guidelines exclude proxies and scrapers. [Fair use](https://vercel.com/docs/limits/fair-use-guidelines) |

These recipes are based on the package layout and provider documentation checked in November 2026. The pre-existing Firebase site is live. Other providers are compatibility candidates that need a real deploy and acceptance check.

Open the published URL over HTTPS. Import a small local recording, export it and play the saved file. Check a reload on a phone, then try an offline reload after the site has loaded and cached its core files. Test separation separately after importing the model. If you see a blank screen or old version, verify the upload folder and deployment status before changing browser storage.

The browser app looks for optional server services at the same site's `/api/` addresses. The grabber's direct handoff currently supports the official Firebase site and local SoundLab addresses. On a self-hosted copy, **save a file in the extension, then import it into your copy of SoundLab**. A public site cannot call your local helper.

## Publish the Laravel editor and server

The current PHP package works with a compatible host. The published ZIP includes “AlwaysData” in its name because the original instructions used that provider. Other hosts must meet the same requirements.

| Option | What to expect |
| --- | --- |
| **AlwaysData Free** | A candidate for personal installations with PHP 8.4+. Follow the [PHP deployment steps](../DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md) and verify the runtime and storage limits on your account. [Plan](https://www.alwaysdata.com/en/offers/) |
| **Another PHP host with a configurable web root** | Check PHP 8.4.1 or later in the PHP 8 series, required PHP modules, writable disk, HTTPS, a private database, and a way to run migrations and cleanup. Publish only the app's `public/` folder. |
| **InfinityFree / Freehostia** | Their published per-file limits are below the included 20.7 MiB browser runtime. InfinityFree also restricts the web root and scheduled jobs. A modified package and a private-file verification would be required. [InfinityFree limits](https://forum.infinityfree.com/t/file-size-and-upload-limits/49308), [Freehostia limits](https://www.freehostia.com/free-cloud-hosting/) |
| **AwardSpace Free** | Its free plan disables outbound and process functions used by the server media workflow. [Function restrictions](https://www.awardspace.com/kb/disabled-php-functions/) |
| **Render Free** | A candidate for a disposable container demo. Its free service loses local files on restarts and sleep, so the current file-storage setup needs adaptation for durable use. [Free-service limits](https://render.com/docs/free) |

Follow the [PHP setup and upgrade guide](../DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md) for the environment, migration and health check. Keep the private environment file and database outside the published folder. Verify that the host denies requests for those files before sharing the URL. Server extractors require additional tools and network protections. Begin with them disabled.

Back up the database, media and private environment before replacing a Laravel install. Before moving the browser editor to a different address, save local recordings and export session metadata from the original address. Visitors can keep using the existing browser or installed app if a free hosting account runs out of quota.
