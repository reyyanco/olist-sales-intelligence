# Diğer betiklerin ortak kullandığı yardımcılar. Doğrudan çalıştırılmaz.
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "docker komutu bulunamadı. Docker Desktop'ın çalıştığından emin olun ve terminali yeniden açın."
}

function Assert-EnvFile {
    if (-not (Test-Path (Join-Path $ProjectRoot '.env'))) {
        throw ".env bulunamadı. Önce .\scripts\new-env.ps1 çalıştırın."
    }
}

function Get-EnvValue([string]$Name) {
    # .env içinden gizli olmayan bir değeri okur (ör. POSTGRES_DB). Parola anahtarları için kullanılmaz.
    if ($Name -like '*PASSWORD*') { throw "Get-EnvValue parola okumak için kullanılmaz: $Name" }
    $line = Select-String -Path (Join-Path $ProjectRoot '.env') -Pattern "^$Name=(.*)$" | Select-Object -First 1
    if (-not $line) { throw "$Name .env içinde tanımlı değil." }
    return $line.Matches[0].Groups[1].Value.Trim()
}

function Invoke-Compose {
    # Docker ilerleme bilgisini stderr'e yazar. Windows PowerShell 5.1'de çıktı
    # yönlendirildiğinde bu satırlar hata kaydına dönüşür; başarı çıkış koduyla ölçülür.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & docker compose @args
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($args -join ' ') başarısız oldu (çıkış kodu $LASTEXITCODE)."
    }
}
