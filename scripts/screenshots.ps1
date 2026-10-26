# Çalışan dashboard'un gerçek ekran görüntülerini alır ve arayüz etkileşimlerini kontrol eder (Playwright).
# Önce: .\scripts\dashboard.ps1   Çıktı: docs/screenshots/ (*.png, report.json, interactions.json)
#
#   .\scripts\screenshots.ps1 -LocalChrome   # bilgisayarda kurulu Google Chrome (Aşama 7'de kullanıldı)
#   .\scripts\screenshots.ps1                # resmî Playwright Docker imajı (sonucu: docs/validation_report.md)
#   -OutDir <klasör>                         # çıktı klasörü (varsayılan: docs\screenshots)
#   -OverviewOnly                            # yalnızca Genel Bakış görüntüleri ve etkileşimleri; diğer kayıtlar korunur
param([switch]$LocalChrome, [string]$OutDir = 'docs\screenshots', [switch]$OverviewOnly)
. "$PSScriptRoot\_common.ps1"

$out = Join-Path $ProjectRoot $OutDir
New-Item -ItemType Directory -Force $out | Out-Null
$mode = if ($OverviewOnly) { 'overview' } else { 'all' }

if ($LocalChrome) {
    # Playwright Python paketi proje içinde, git dışı bir sanal ortama kurulur; tarayıcı indirilmez,
    # kurulu Chrome kullanılır (PW_CHANNEL=chrome).
    $venv = Join-Path $ProjectRoot 'tools\.venv'
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
        & python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Sanal ortam oluşturulamadı." }
        & (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check -q 'playwright==1.64.0'
        if ($LASTEXITCODE -ne 0) { throw "Playwright kurulamadı." }
    }
    $env:PW_CHANNEL = 'chrome'
    & (Join-Path $venv 'Scripts\python.exe') (Join-Path $ProjectRoot 'tools\screenshots.py') 'http://127.0.0.1:8501' $out $mode
} else {
    # Resmî imaj, digest ile sabitlenmiş (Aşama 8'de indirildi). İmajda tarayıcılar var ama Python
    # "playwright" paketi YOK; imajdaki tarayıcı sürümüyle aynı paket her çalıştırmada kurulur (PyPI).
    $image = 'mcr.microsoft.com/playwright/python:v1.64.1-noble@sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031'
    & docker run --rm --network 'olist-sales-intelligence_default' `
        -v "${ProjectRoot}\tools:/tools:ro" -v "${out}:/out" `
        $image sh -c "pip install -q --disable-pip-version-check --root-user-action=ignore playwright==1.64.1 && python /tools/screenshots.py http://dashboard:8501 /out $mode"
}
if ($LASTEXITCODE -ne 0) { throw "Ekran görüntüsü / etkileşim kontrolü başarısız (çıkış kodu $LASTEXITCODE)." }
