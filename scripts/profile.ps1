# data/raw altındaki gerçek Olist CSV dosyalarının profilini docs/data_profile.md dosyasına yazar.
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

Invoke-Compose run --rm --no-deps -v "${ProjectRoot}\docs:/app/docs" etl python -m etl profile --source data/raw --output docs/data_profile.md
