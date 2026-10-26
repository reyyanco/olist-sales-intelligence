# Temiz kurulum doğrulaması (docs/validation_report.md).
# AYRI bir Compose projesi ("olist-validation"), ayrı volume ve ayrı dashboard portu (8502) kullanır;
# ana projenin (olist-sales-intelligence) verisine, volume'una ve konteynerlerine dokunmaz.
# Akış: şema -> ETL (2 kez) -> kalite kontrolleri -> bağımsız gerçek veri kontrolleri -> rapor rutinleri ->
#       kontrollü başarısızlık -> pytest -> dashboard -> KPI doğrulaması -> tarayıcıda arayüz kontrolü.
# Sonuçlar: docs/validation/*.json. -Keep verilmezse sonunda YALNIZCA doğrulama projesi ve volume'u silinir.
param([switch]$Keep)
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

$P = 'olist-validation'
if ($P -eq 'olist-sales-intelligence') { throw "Doğrulama projesi ana projeyle aynı olamaz." }
$env:DASHBOARD_PORT = '8502'
$outDir = Join-Path $ProjectRoot 'docs\validation'
New-Item -ItemType Directory -Force $outDir | Out-Null
$mounts = @('-v', "${ProjectRoot}\validation:/app/validation:ro", '-v', "${ProjectRoot}\docs:/app/docs",
            '-v', "${ProjectRoot}\dashboard:/app/dashboard:ro")
$steps = [System.Collections.Generic.List[object]]::new()

function Step([string]$name, [scriptblock]$block) {
    $started = Get-Date
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { $output = & $block 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $prev }
    $code = $LASTEXITCODE
    $steps.Add([ordered]@{ step = $name; exit_code = $code; seconds = [math]::Round(((Get-Date) - $started).TotalSeconds, 1);
                           tail = @($output | Select-Object -Last 6) })
    Write-Host ("{0,-38} çıkış={1} ({2:N1} s)" -f $name, $code, ((Get-Date) - $started).TotalSeconds)
    return $code
}
function VC { & docker compose -p $P @args }

Step '00_teardown_previous_validation' { VC --profile '*' down --volumes --remove-orphans } | Out-Null
Step '01_build_image' { VC build app } | Out-Null
Step '02_db_up_fresh_volume' { VC up -d --wait db } | Out-Null
Step '03_etl_run_first_load' { VC run --rm etl python -m etl run } | Out-Null
Step '04_snapshot_after_first_load' { VC run --rm @mounts etl python -m validation.checks snapshot --output docs/validation/snapshot_first_load.json } | Out-Null
Step '05_etl_run_second_load' { VC run --rm etl python -m etl run } | Out-Null
Step '06_snapshot_after_second_load' { VC run --rm @mounts etl python -m validation.checks snapshot --output docs/validation/snapshot_second_load.json } | Out-Null
Step '07_invariants_real_data' { VC run --rm @mounts etl python -m validation.checks invariants --output docs/validation/invariants.json } | Out-Null
Step '08_setup_dashboard_role_1' { VC run --rm etl python -m etl setup-dashboard-role } | Out-Null
Step '09_setup_dashboard_role_2' { VC run --rm etl python -m etl setup-dashboard-role } | Out-Null
Step '10_routines_repeat' { VC run --rm @mounts etl python -m validation.checks routines --output docs/validation/routines.json } | Out-Null
Step '11_controlled_failure' { VC run --rm @mounts etl python -m validation.checks controlled-failure --output docs/validation/controlled_failure.json } | Out-Null
Step '12_etl_runs_listing' { VC run --rm etl python -m etl runs --limit 5 } | Out-Null
Step '13_pytest_clean_cluster' { VC run --rm tests pytest -q } | Out-Null
Step '14_dashboard_up_8502' { VC --profile dashboard up -d --wait dashboard } | Out-Null
Step '15_dashboard_kpi_vs_direct_sql' { VC run --rm @mounts etl python -m dashboard.verify --output docs/validation/dashboard_verification.json } | Out-Null
$venvPy = Join-Path $ProjectRoot 'tools\.venv\Scripts\python.exe'
if (Test-Path $venvPy) {
    $env:PW_CHANNEL = 'chrome'
    Step '16_browser_ui_checks_8502' { & $venvPy (Join-Path $ProjectRoot 'tools\screenshots.py') 'http://127.0.0.1:8502' (Join-Path $outDir 'screenshots') } | Out-Null
} else {
    $steps.Add([ordered]@{ step = '16_browser_ui_checks_8502'; exit_code = $null; seconds = 0;
                           tail = @('ÇALIŞTIRILAMADI: tools\.venv yok (önce .\scripts\screenshots.ps1 -LocalChrome)') })
}

$a = Get-Content (Join-Path $outDir 'snapshot_first_load.json') -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
$b = Get-Content (Join-Path $outDir 'snapshot_second_load.json') -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
$same = $a -and $b -and (($a.result | ConvertTo-Json -Depth 5) -eq ($b.result | ConvertTo-Json -Depth 5))
$steps.Add([ordered]@{ step = '17_second_load_identical'; exit_code = $(if ($same) { 0 } else { 1 }); seconds = 0;
                       tail = @("snapshots identical: $same") })

if (-not $Keep) { Step '99_teardown_validation_only' { VC --profile '*' down --volumes --remove-orphans } | Out-Null }

$steps | ConvertTo-Json -Depth 5 | Out-File -Encoding utf8 (Join-Path $outDir 'clean_install_steps.json')
$failed = @($steps | Where-Object { $_.exit_code -ne 0 })
Write-Host ("Adım: {0}, başarısız/çalıştırılamayan: {1}" -f $steps.Count, $failed.Count)
if ($failed.Count) { $failed | ForEach-Object { Write-Host "  - $($_.step) (çıkış=$($_.exit_code))" }; exit 1 }
