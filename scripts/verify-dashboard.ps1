# Gerçek veride örnek filtrelerdeki dashboard KPI'larını doğrudan SQL ile karşılaştırır.
# Sonuç: docs/dashboard_verification.json (eşleşmeyen varsa çıkış kodu 1).
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

Invoke-Compose run --rm -v "${ProjectRoot}\docs:/app/docs" -v "${ProjectRoot}\dashboard:/app/dashboard:ro" etl python -m dashboard.verify --output docs/dashboard_verification.json
