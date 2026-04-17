chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientDir = Join-Path $scriptDir "client"
$venv = Join-Path $scriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }
$clientScript = Join-Path $clientDir "client.py"

& $venv $clientScript
