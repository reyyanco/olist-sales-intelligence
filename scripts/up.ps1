# Ortamı başlatır: Python imajını derler, PostgreSQL'i başlatır ve sağlıklı olmasını bekler.
. "$PSScriptRoot\_common.ps1"
Assert-EnvFile

Invoke-Compose build app
Invoke-Compose up -d --wait db
Invoke-Compose ps db
