# Günlük durdurma: tüm servisleri durdurur ve konteynerleri kaldırır.
# Veritabanı volume'u (pgdata) KORUNUR; veriler silinmez.
. "$PSScriptRoot\_common.ps1"

Invoke-Compose --profile '*' down
Write-Host "Servisler durduruldu. Veritabanı verisi korundu."
