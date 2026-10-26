# ETL'i tek seferlik konteynerde çalıştırır: migrate + data/raw yükleme + dw dönüşümü + doğrulama.
# Ek argümanlar etl komutuna geçer, örnek: .\scripts\etl.ps1 check | migrate | verify
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

if ($args.Count -gt 0) {
    Invoke-Compose run --rm etl python -m etl @args
} else {
    Invoke-Compose run --rm etl
}
