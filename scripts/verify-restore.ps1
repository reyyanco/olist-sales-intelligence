# Geri yüklenen veritabanını kaynak veritabanıyla karşılaştırır ve kalite kontrollerini hedefte çalıştırır.
#
#   .\scripts\verify-restore.ps1 -BackupFile backups\olist_....dump              # hedef: olist_restore_test
#   .\scripts\verify-restore.ps1 -TargetDatabase olist_restore_test -DropAfter   # başarılıysa hedefi siler
#
# Karşılaştırma (sql/maintenance/database_snapshot.sql, iki veritabanında aynı sorgu):
#   - nesne sayıları (şema başına tablo, view, MV, indeks, rutin, kısıt)
#   - iş verisi: staging/dw/reporting tablolarının satır sayıları, içerik MD5'leri, finansal toplamlar
#   - çalışma kayıtları (meta) AYRI değerlendirilir: yedekten sonra kaynakta yeni ETL çalıştıysa yalnızca
#     bu bölüm farklı çıkar ve böyle raporlanır
#   - dashboard okuma rolünün yetkileri
# Ayrıca hedefte "python -m etl verify" (sql/tests) çalışır. Sonuç: docs/validation/backup_restore_check.json
# -DropAfter yalnızca adı "_restore_test" ile biten bir hedefi ve yalnızca tüm kontroller geçtiyse siler.
param(
    [string]$TargetDatabase = 'olist_restore_test',
    [string]$BackupFile,
    [switch]$DropAfter
)
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

if ($TargetDatabase -notmatch '^[a-z_][a-z0-9_]{0,62}$') { throw "Geçersiz veritabanı adı: $TargetDatabase" }
$source = Get-EnvValue 'POSTGRES_DB'
$user = Get-EnvValue 'POSTGRES_USER'
if ($TargetDatabase -eq $source) { throw "Hedef ile kaynak aynı olamaz: $source" }

$sqlFile = Join-Path $ProjectRoot 'sql\maintenance\database_snapshot.sql'
$containerSql = '/tmp/database_snapshot.sql'
Invoke-Compose cp $sqlFile "db:$containerSql"
try {
    $snap = @{}
    foreach ($database in @($source, $TargetDatabase)) {
        $json = Invoke-Compose exec -T db psql -U $user -w -X -v ON_ERROR_STOP=1 -At -d $database -f $containerSql
        $snap[$database] = ($json -join '') | ConvertFrom-Json
    }
} finally {
    Invoke-Compose exec -T db rm -f $containerSql
}
$a = $snap[$source]; $b = $snap[$TargetDatabase]

function Compare-Map($left, $right) {
    # İki JSON nesnesinin anahtar bazında farkları (eksik anahtar veya farklı değer).
    $keys = @($left.PSObject.Properties.Name) + @($right.PSObject.Properties.Name) | Sort-Object -Unique
    @(foreach ($k in $keys) {
        $l = $left.$k | ConvertTo-Json -Depth 10 -Compress
        $r = $right.$k | ConvertTo-Json -Depth 10 -Compress
        if ($l -ne $r) { [ordered]@{ key = $k; source = $l; restored = $r } }
    })
}

$sections = [ordered]@{
    objects                      = Compare-Map $a.objects $b.objects
    business_row_counts          = Compare-Map $a.business.row_counts $b.business.row_counts
    business_content_md5         = Compare-Map $a.business.content_md5 $b.business.content_md5
    business_financials          = Compare-Map $a.business.financials $b.business.financials
    materialized_views_populated = Compare-Map $a.business.materialized_views_populated $b.business.materialized_views_populated
    logs                         = Compare-Map $a.logs $b.logs
    privileges                   = Compare-Map $a.privileges $b.privileges
}

# Hedefte kalite kontrolleri (sql/tests). Windows PowerShell konteyner çıktısındaki Türkçe karakterleri
# bozabildiği için sonuç, günlük düzeyinden (INFO = geçti, ERROR = başarısız) ve dosya adından okunur.
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
try {
    $verifyOut = & docker compose run --rm -e "POSTGRES_DB=$TargetDatabase" etl python -m etl verify 2>&1 | ForEach-Object { "$_" }
    $verifyExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prevEap
}
$verifyLines = @($verifyOut | ForEach-Object {
    if ($_ -match '^(INFO|ERROR) .*?(\d{3}_[a-z0-9_]+\.sql)') { '{0}: {1}' -f $(if ($Matches[1] -eq 'INFO') { 'passed' } else { 'failed' }), $Matches[2] }
})

$businessOk = ($sections.objects.Count + $sections.business_row_counts.Count + $sections.business_content_md5.Count +
               $sections.business_financials.Count + $sections.materialized_views_populated.Count +
               $sections.privileges.Count) -eq 0
$logsOk = $sections.logs.Count -eq 0
$verifyOk = $verifyExit -eq 0

$backup = $null
if ($BackupFile) {
    $f = Get-Item (Resolve-Path $BackupFile)
    $backup = [ordered]@{ file = "backups/$($f.Name)"; bytes = $f.Length;
                          sha256 = (Get-FileHash -Algorithm SHA256 $f.FullName).Hash.ToLowerInvariant() }
}
$result = [ordered]@{
    checked_at_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    source_database = $source
    restored_database = $TargetDatabase
    backup = $backup
    scope = 'business = staging+dw+reporting (row counts, content MD5, financial totals, MV state), objects, reader-role privileges; logs = meta schema, evaluated separately'
    business_and_objects_identical = $businessOk
    logs_identical = $logsOk
    etl_verify_on_restored = [ordered]@{ exit_code = $verifyExit; lines = $verifyLines }
    differences = $sections
    database_size_bytes = [ordered]@{ source = $a.database_size_bytes; restored = $b.database_size_bytes }
    tables_compared = @($a.business.row_counts.PSObject.Properties).Count + @($a.logs.row_counts.PSObject.Properties).Count
    source_snapshot = $a
    restored_snapshot = $b
}
$outFile = Join-Path $ProjectRoot 'docs\validation\backup_restore_check.json'
New-Item -ItemType Directory -Force (Split-Path $outFile) | Out-Null
[System.IO.File]::WriteAllText($outFile, ($result | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding $false))

Write-Host ("Karşılaştırılan tablo/MV: {0}" -f $result.tables_compared)
Write-Host ("İş verisi, nesneler ve yetkiler aynı: {0}" -f $businessOk)
Write-Host ("Çalışma kayıtları (meta) aynı: {0}" -f $logsOk)
Write-Host ("Hedefte kalite kontrolleri: çıkış {0}; {1} satır" -f $verifyExit, $verifyLines.Count)
$sections.GetEnumerator() | Where-Object { $_.Value.Count } | ForEach-Object {
    Write-Host ("  Fark [{0}]: {1}" -f $_.Key, (($_.Value | ForEach-Object { $_.key }) -join ', '))
}
Write-Host "Sonuç: docs\validation\backup_restore_check.json"

if (-not ($businessOk -and $verifyOk)) {
    Write-Host "Doğrulama BAŞARISIZ; hedef veritabanı incelemek için bırakıldı: $TargetDatabase"
    exit 1
}
if (-not $logsOk) {
    Write-Warning "Çalışma kayıtları farklı: yedekten sonra kaynakta ETL/yenileme çalışmış olabilir (ayrıntı JSON'da)."
}
if ($DropAfter) {
    if ($TargetDatabase -notmatch '_restore_test$') {
        Write-Warning "-DropAfter yalnızca adı _restore_test ile biten veritabanlarını siler; $TargetDatabase silinmedi."
    } else {
        Invoke-Compose exec -T db dropdb -U $user -w $TargetDatabase
        Write-Host "Geri yükleme deneme veritabanı silindi: $TargetDatabase"
    }
}
