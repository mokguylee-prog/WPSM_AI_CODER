chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientDir = Join-Path $scriptDir "client"
$venv = Join-Path $scriptDir "venv\Scripts\python.exe"
if (-not (Test-Path $venv)) { $venv = "python" }
$guiScript = Join-Path $clientDir "gui_client.py"
$serverLauncher = Join-Path $scriptDir "server\server.py"

function Test-ServerHealthy {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8888/health" -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-ServerHealthy)) {
    Write-Host "Sm_AICoder 서버가 오프라인입니다. 백그라운드에서 서버를 시작합니다..."
    Start-Process -FilePath $venv -ArgumentList "-X utf8 `"$serverLauncher`"" -WorkingDirectory $scriptDir -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 1
}

Write-Host "Sm_AICoder GUI 클라이언트를 시작합니다..."
& $venv -X utf8 $guiScript
