# Deploy the PHP package

Use `NTK_SoundLab_Studio_AlwaysData-2026.11.16.1.zip` from the [release page](https://github.com/appdevmanwill/NTK-SoundLab-Studio/releases/tag/v2026.11.16.1).

The archive contains Laravel 13, production Composer dependencies and the shared browser app. It has passed a local startup and database migration test. The target AlwaysData account still needs its own checks.

## Host requirements

The host needs a supported PHP version satisfying `^8.4.1`, outbound HTTPS with a valid certificate store, and the extensions required by Composer. The app uses fileinfo and either SQLite or MySQL, depending on the database configuration.

The site's document root must point to the application's `public/` directory. The web user needs write access to `storage/` and `bootstrap/cache/`. With SQLite, it also needs access to the database file and its directory.

Check these capabilities on the hosting plan before uploading. Server extraction and conversion need additional tools and network controls.

## New installation

Extract the archive into a directory such as `/home/username/soundlab`.

```sh
unzip -q NTK_SoundLab_Studio_AlwaysData-2026.11.16.1.zip -d /home/username/soundlab
cd /home/username/soundlab
cp .env.example .env
```

Set the environment for the real domain.

```ini
APP_NAME="NTK SoundLab Studio"
APP_ENV=production
APP_DEBUG=false
APP_URL=https://your-account.alwaysdata.net
DB_CONNECTION=sqlite
```

Generate an application key and prepare the database.

```sh
php artisan key:generate
touch database/database.sqlite
php artisan migrate --force
```

In the AlwaysData site settings, choose the matching PHP version and set the root to `/home/username/soundlab/public`. Use the actual account name and installation path.

## Updating an existing installation

Back up the database, private files and environment before changing the release. Extract the new package into a separate directory and retain the existing `.env`, `APP_KEY` and database.

Review and run pending migrations against that existing database. Check the new directory before switching the site's document root. Keep the previous directory available for rollback. Database rollback needs its own recovery plan after migrations or new writes.

## Temporary files

The backend includes a prune command for old download jobs and files.

```sh
php /home/username/soundlab/artisan omni:prune --max-age=30
```

The same command is registered with Laravel's scheduler every 30 minutes. Configure either the standard Laravel scheduler or an equivalent scheduled task for this command on the host.

## Extraction and conversion

Set `YT_DLP_PATH` or `FFMPEG_PATH` only when those tools are installed and supported by the hosting plan. Cookie administration requires a server `ADMIN_KEY`.

Keep `MEDIA_EXTRACTOR_EGRESS_SANDBOXED=false` until the host enforces public-network-only access for extractor subprocesses on every connection. The flag records that external control. It does not configure a sandbox.

Browser editing and the optional hosted media services have different requirements. Use `/api/health` to inspect what the running server reports.

## Check the deployed site

Open the app over HTTPS and confirm that local file import and an audio export work. Check that `/api/health` returns a successful status.

Direct requests for `/.env` and `/.git/config` should return 404 or another denial. Anonymous cookie administration should be denied. Confirm that temporary files are pruned, then test a permitted media URL if the server extractor is enabled.
