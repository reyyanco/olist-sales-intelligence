# Bir yedeği (backups\*.dump) AYRI bir veritabanına geri yükler. Varsayılan hedef: olist_restore_test
#
#   .\scripts\restore.ps1 -BackupFile backups\olist_20261025_160000.dump
#   .\scripts\restore.ps1 -BackupFile backups\... -TargetDatabase olist_restore_test
#
# Güvenlik kuralı: hedef veritabanı YOKSA oluşturulur; VARSA tamamen boş olmalıdır. Dolu bir veritabanının
# (ör. ana "olist") üzerine hiçbir koşulda yazılmaz ve hiçbir veritabanı veya volume silinmez.
# Geri yükleme tek işlemdedir (--single-transaction --exit-on-error): hata olursa hedefte yarım veri kalmaz.
# Yedekte olmayan küme düzeyi ayarlar (roller, parolalar, veritabanı CONNECT yetkisi) için README'ye bakın;
# bu betik yalnızca parolasız olist_reporting_reader rolünü (yoksa) ve CONNECT yetkisini yeniden oluşturur.
# Sonuç doğrulaması: .\scripts\verify-restore.ps1
param(
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [string]$TargetDatabase = 'olist_restore_test'
)
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

if ($TargetDatabase -notmatch '^[a-z_][a-z0-9_]{0,62}$') {
    throw "Hedef veritabanı adı küçük harf, rakam ve alt çizgiden oluşmalı: $TargetDatabase"
}
$file = Resolve-Path $BackupFile -ErrorAction Stop
$user = Get-EnvValue 'POSTGRES_USER'

# 1. Dosya bütünlüğü: backup.ps1'in yazdığı SHA-256 ile karşılaştır.
$hashFile = "$file.sha256"
$hash = (Get-FileHash -Algorithm SHA256 $file).Hash.ToLowerInvariant()
if (Test-Path $hashFile) {
    $expected = ((Get-Content $hashFile -TotalCount 1) -split '\s+')[0].ToLowerInvariant()
    if ($expected -ne $hash) { throw "SHA-256 eşleşmiyor; yedek dosyası bozulmuş veya değişmiş: $file" }
    Write-Host "SHA-256 doğrulandı."
} else {
    Write-Warning "SHA-256 dosyası yok ($hashFile); bütünlük karşılaştırılamadı."
}

function Invoke-Psql([string]$Database, [string]$Sql) {
    # Hedef adı yukarıdaki düzenli ifadeyle doğrulandı; SQL'e yalnızca bu ad girer.
    Invoke-Compose exec -T db psql -U $user -w -X -v ON_ERROR_STOP=1 -At -d $Database -c $Sql
}

# 2. Hedef yoksa oluştur; varsa boş olduğunu doğrula.
$exists = Invoke-Psql 'postgres' "SELECT count(*) FROM pg_database WHERE datname = '$TargetDatabase'"
if ([int]$exists -eq 0) {
    Invoke-Compose exec -T db createdb -U $user -w $TargetDatabase
    Write-Host "Veritabanı oluşturuldu: $TargetDatabase"
} else {
    $objects = Invoke-Psql $TargetDatabase ("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace " +
        "WHERE n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname NOT LIKE 'pg_toast%' " +
        "AND n.nspname NOT LIKE 'pg_temp%'")
    $schemas = Invoke-Psql $TargetDatabase ("SELECT count(*) FROM pg_namespace WHERE nspname NOT IN " +
        "('public', 'pg_catalog', 'information_schema') AND nspname NOT LIKE 'pg_toast%' AND nspname NOT LIKE 'pg_temp%'")
    if ([int]$objects -ne 0 -or [int]$schemas -ne 0) {
        throw "Hedef veritabanı '$TargetDatabase' boş değil ($objects nesne, $schemas şema). Üzerine yazılmaz; başka bir ad seçin."
    }
    Write-Host "Mevcut ve boş veritabanı kullanılacak: $TargetDatabase"
}

# 3. Yedekteki GRANT'ların bağlı olduğu, küme düzeyindeki parolasız rol (sql/180 ile aynı tanım).
Invoke-Psql 'postgres' ("DO `$`$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'olist_reporting_reader') " +
    "THEN CREATE ROLE olist_reporting_reader NOLOGIN; END IF; END `$`$") | Out-Null

# 4. Geri yükleme: dosya konteynere kopyalanır, tek işlemde yüklenir, geçici dosya silinir.
$containerFile = "/tmp/restore_$([guid]::NewGuid().ToString('N')).dump"
$started = Get-Date
try {
    Invoke-Compose cp $file.Path "db:$containerFile"
    Invoke-Compose exec -T db pg_restore -U $user -w -d $TargetDatabase --single-transaction --exit-on-error $containerFile
} finally {
    Invoke-Compose exec -T db rm -f $containerFile
}

# 5. Veritabanı düzeyi yetki yedekte yoktur (pg_dump -C olmadan); sql/180'deki gibi yeniden verilir.
Invoke-Psql $TargetDatabase "GRANT CONNECT ON DATABASE $TargetDatabase TO olist_reporting_reader" | Out-Null

Write-Host ("Geri yükleme tamamlandı: {0} ({1:N1} s). Doğrulama: .\scripts\verify-restore.ps1 -TargetDatabase {0} -BackupFile {2}" -f `
    $TargetDatabase, ((Get-Date) - $started).TotalSeconds, $BackupFile)
