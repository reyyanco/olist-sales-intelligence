# .env.example dosyasından .env oluşturur; parola alanlarını (*_PASSWORD) rastgele üretir.
# .env zaten varsa mevcut değerlere DOKUNMAZ; yalnızca .env.example'da olup .env'de olmayan anahtarları ekler.
# Parolalar ekrana yazılmaz.
. "$PSScriptRoot\_common.ps1"

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    # Yalnızca harf ve rakam: Compose ve bağlantı URL'lerinde kaçış gerektirmez.
    -join ($bytes | ForEach-Object { '{0:x2}' -f $_ })
}

function Resolve-Line([string]$line) {
    if ($line -match '^([A-Z0-9_]+_PASSWORD)=') { return "$($Matches[1])=$(New-Secret)" }
    return $line
}

$envPath = Join-Path $ProjectRoot '.env'
$exampleLines = Get-Content (Join-Path $ProjectRoot '.env.example')
$utf8 = New-Object System.Text.UTF8Encoding $false

if (-not (Test-Path $envPath)) {
    $content = ($exampleLines | ForEach-Object { Resolve-Line $_ }) -join "`n"
    [System.IO.File]::WriteAllText($envPath, $content + "`n", $utf8)
    Write-Host ".env oluşturuldu (parolalar rastgele üretildi, gösterilmiyor)."
    exit 0
}

$existingKeys = @(Get-Content $envPath | Where-Object { $_ -match '^[A-Z0-9_]+=' } | ForEach-Object { ($_ -split '=', 2)[0] })
$added = @()
$newLines = foreach ($line in $exampleLines) {
    if ($line -match '^([A-Z0-9_]+)=' -and $existingKeys -notcontains $Matches[1]) {
        $added += $Matches[1]
        Resolve-Line $line
    }
}
if ($added.Count -eq 0) {
    Write-Host ".env zaten güncel; değiştirilmedi."
    exit 0
}
$current = [System.IO.File]::ReadAllText($envPath)
if (-not $current.EndsWith("`n")) { $current += "`n" }
[System.IO.File]::WriteAllText($envPath, $current + (($newLines) -join "`n") + "`n", $utf8)
Write-Host ".env içine eksik anahtarlar eklendi: $($added -join ', ') (parolalar gösterilmiyor)."
