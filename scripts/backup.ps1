# Ana veritabanının (.env: POSTGRES_DB) yedeğini alır. Çalışan "db" konteynerindeki PostgreSQL 16 pg_dump'ı
# özel biçimde (-Fc, sıkıştırılmış) kullanılır. Çıktı: backups\<veritabanı>_YYYYMMDD_HHmmss.dump ve .sha256
#
# İkili dosya PowerShell çıktı yönlendirmesinden (>) GEÇMEZ: pg_dump dosyayı konteynerin içine yazar,
# "docker compose cp" bayt bayt kopyalar; iki taraftaki SHA-256 karşılaştırılır.
# Parola gerekmez ve yazılmaz: pg_dump konteynerin içinden yerel soketle bağlanır.
# Yedekte OLMAYANLAR (rol, parola, sunucu ayarı vb.): README "Yedekleme ve geri yükleme".
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

$db = Get-EnvValue 'POSTGRES_DB'
$user = Get-EnvValue 'POSTGRES_USER'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$name = "${db}_${stamp}.dump"
$containerFile = "/tmp/$name"
$backupDir = Join-Path $ProjectRoot 'backups'
$hostFile = Join-Path $backupDir $name
New-Item -ItemType Directory -Force $backupDir | Out-Null

try {
    Invoke-Compose exec -T db pg_dump -U $user -w -d $db -Fc -f $containerFile
    # Dosyanın okunabilir bir arşiv olduğunu doğrula (içindekiler listesi).
    $entries = @(Invoke-Compose exec -T db pg_restore --list $containerFile | Where-Object { $_ -and $_ -notmatch '^;' })
    $containerHash = ((Invoke-Compose exec -T db sha256sum $containerFile) -split '\s+')[0].ToLowerInvariant()
    Invoke-Compose cp "db:$containerFile" $hostFile
} finally {
    Invoke-Compose exec -T db rm -f $containerFile
}

$hostHash = (Get-FileHash -Algorithm SHA256 $hostFile).Hash.ToLowerInvariant()
if ($hostHash -ne $containerHash) {
    throw "Kopyalanan yedeğin SHA-256 değeri konteynerdekiyle aynı değil; dosya güvenilir değil: $hostFile"
}
[System.IO.File]::WriteAllText("$hostFile.sha256", "$hostHash  $name`n", (New-Object System.Text.UTF8Encoding $false))

$size = (Get-Item $hostFile).Length
Write-Host ("Yedek alındı: backups\{0} ({1:N0} bayt, {2} arşiv girdisi)" -f $name, $size, $entries.Count)
Write-Host "SHA-256: $hostHash (backups\$name.sha256)"
Write-Host "Geri yükleme denemesi: .\scripts\restore.ps1 -BackupFile backups\$name"
