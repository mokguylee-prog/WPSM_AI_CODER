chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverDir = Join-Path $scriptDir "server"
$venv = Join-Path $scriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }
$serverLauncher = Join-Path $serverDir "server.py"

Write-Host "Sm_AICoder 서버를 시작합니다..."
& $venv -X utf8 $serverLauncher
