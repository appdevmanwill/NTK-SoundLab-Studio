# SoundLab on PHP hosting

Use the [PHP deployment guide](../DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md) for the current archive, environment setup and health checks.

For Hostinger, select a PHP version that satisfies `^8.4.1` and configure the site so that its document root points to the application's `public/` directory. Confirm the required extensions, writable directories and scheduled-task support on the chosen hosting plan.

The current archive has been tested locally. Hostinger deployment and server-side extraction have not been verified for this release.
