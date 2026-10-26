# Testleri tek seferlik konteynerde, ayrı test veritabanında çalıştırır.
# Ek argümanlar pytest'e geçer, örnek: .\scripts\test.ps1 -k sql_runner -v
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

Invoke-Compose run --rm tests pytest @args
