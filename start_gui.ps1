chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientDir = Join-Path $scriptDir "client"
$venv = Join-Path $scriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }
$guiScript = Join-Path $clientDir "gui_client.py"

Write-Host "Sm_AICoder GUI 클라이언트 시작..."
& $venv $guiScript
