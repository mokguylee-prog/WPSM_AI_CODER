chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $scriptDir "server\server.pid"
if (-not (Test-Path $pidFile)) {
    Write-Host "server.pid 없음 - 서버가 실행 중이지 않습니다."
    exit
}

$serverPid = [int]((Get-Content $pidFile).Trim())
Write-Host "종료 시도 중... (PID: $serverPid)"

$result = taskkill /PID $serverPid /F 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "서버 종료 완료 (PID: $serverPid)"
} else {
    Write-Host "프로세스를 찾을 수 없습니다 (이미 종료됨, PID: $serverPid)"
}

Remove-Item $pidFile -ErrorAction SilentlyContinue
Write-Host "server.pid 삭제 완료"
