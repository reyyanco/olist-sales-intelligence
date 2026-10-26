# SIFIRLAMA: servisleri durdurur ve veritabanı volume'unu SİLER.
# Yüklenmiş tüm veriler kaybolur. data/raw altındaki CSV dosyalarına dokunulmaz.
# Onay için proje adını yazmanız istenir; -Force ile onay atlanır.
param([switch]$Force)
. "$PSScriptRoot\_common.ps1"

$projectName = 'olist-sales-intelligence'
if (-not $Force) {
    Write-Warning "Bu işlem PostgreSQL verilerini (volume: ${projectName}_pgdata) kalıcı olarak siler."
    $answer = Read-Host "Devam etmek için proje adını yazın ($projectName)"
    if ($answer -ne $projectName) {
        Write-Host "İptal edildi; hiçbir şey silinmedi."
        exit 1
    }
}

Invoke-Compose --profile '*' down --volumes --remove-orphans
Write-Host "Ortam sıfırlandı; veritabanı volume'u silindi."
