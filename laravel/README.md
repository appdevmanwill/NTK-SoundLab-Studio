# SoundLab PHP backend

This is the optional Laravel backend for SoundLab. It serves the studio and handles supported media requests, job state and temporary downloads.

The current lock file uses Laravel 13 and requires PHP `^8.4.1`. A static web or packaged desktop installation can use local editing without this backend.

## Run a fresh local checkout

Install Composer dependencies in this directory.

```sh
composer install
```

For a new installation, copy `.env.example` to `.env`, generate an application key and create the SQLite database.

```sh
cp .env.example .env
php artisan key:generate
php -r "touch('database/database.sqlite');"
php artisan migrate
php artisan serve --host=127.0.0.1 --port=8000
```

On Windows, use `Copy-Item .env.example .env` for the copy step. Preserve the environment, application key and database when updating an existing installation.

Open `http://127.0.0.1:8000`. The studio uses the shared files in `public/` and the Blade entry views.

## Media services

Configuration is in `config/media.php`. `YT_DLP_PATH` and `FFMPEG_PATH` select optional installed tools. `ADMIN_KEY` controls cookie administration.

External extraction is disabled until `MEDIA_EXTRACTOR_EGRESS_SANDBOXED` records that the host has enforced the required network restrictions for extractor processes. Setting the flag alone does not create those restrictions.

Inspect `/api/health` to see the capabilities reported by the running host. A page loading successfully does not prove that its extractor or converter is available.

## Tests

The test suite uses isolated storage and a test database.

```sh
php vendor/bin/phpunit --do-not-cache-result
```

## Deployment

Use a web root pointing to `public/`, HTTPS, production configuration and writable `storage/` and `bootstrap/cache/` directories. The prepared archive includes production Composer dependencies. [PHP deployment guide](../DEPLOY_MANUAL/ALWAYSDATA_DEPLOYMENT.md)
