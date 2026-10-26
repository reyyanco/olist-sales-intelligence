# Performans deneylerini çalıştırır (docs/performance.md). Ayrı olist_perf veritabanını kullanır;
# ana veritabanına dokunmaz. Örnekler:
#   .\scripts\perf.ps1 --rebuild          # olist_perf'i data/raw'dan yeniden kur + tüm deneyler
#   .\scripts\perf.ps1 --only E1_customer_history,load
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

Invoke-Compose run --rm -v "${ProjectRoot}\docs:/app/docs" -v "${ProjectRoot}\perf:/app/perf:ro" etl python -m perf @args
