# Dashboard'u arka planda başlatır ve sağlıklı olmasını bekler. Yalnızca bu bilgisayardan erişilir.
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

# Şema güncel olmalı ve dashboard'un salt okunur rolü .env'deki değerlerle hazır olmalı.
Invoke-Compose run --rm etl python -m etl migrate
Invoke-Compose run --rm etl python -m etl setup-dashboard-role
# --force-recreate: rol parolası veya ortam değişkenleri değiştiyse konteyner yeni değerlerle başlar.
Invoke-Compose --profile dashboard up -d --wait --force-recreate dashboard

# Compose ile aynı öncelik: ortam değişkeni, sonra .env, sonra 8501.
$port = $env:DASHBOARD_PORT
if (-not $port) { $port = (Select-String -Path (Join-Path $ProjectRoot '.env') -Pattern '^DASHBOARD_PORT=(\d+)' | Select-Object -First 1).Matches.Groups[1].Value }
if (-not $port) { $port = '8501' }
Write-Host "Dashboard: http://127.0.0.1:$port"
