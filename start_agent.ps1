# Sm_AICoder 에이전트 클라이언트 실행
Write-Host "Sm_AICoder Agent Client 시작..." -ForegroundColor Cyan
Write-Host "서버가 먼저 실행 중이어야 합니다. (start_server.ps1)" -ForegroundColor Gray
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& "$scriptDir\venv\Scripts\python.exe" "$scriptDir\client\agent_client.py"
