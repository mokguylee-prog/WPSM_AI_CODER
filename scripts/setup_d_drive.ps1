# Sm_AICoder D드라이브 설치 스크립트
$ErrorActionPreference = "Stop"

Write-Host "=== Sm_AICoder D드라이브 설치 ===" -ForegroundColor Cyan

# 환경변수 설정 (D드라이브)
[System.Environment]::SetEnvironmentVariable("HF_HOME",            "D:\Sm_AICoder\hf_cache", "User")
[System.Environment]::SetEnvironmentVariable("TRANSFORMERS_CACHE", "D:\Sm_AICoder\hf_cache", "User")
[System.Environment]::SetEnvironmentVariable("PIP_CACHE_DIR",      "D:\Sm_AICoder\pip_cache", "User")
$env:HF_HOME = "D:\Sm_AICoder\hf_cache"
$env:PIP_CACHE_DIR = "D:\Sm_AICoder\pip_cache"

Write-Host "환경변수 설정 완료" -ForegroundColor Green

# 디렉토리 생성
$dirs = @(
    "D:\Sm_AICoder\models\gguf",
    "D:\Sm_AICoder\hf_cache",
    "D:\Sm_AICoder\pip_cache"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d | Out-Null }
}
Write-Host "디렉토리 생성 완료" -ForegroundColor Green

# venv 생성
$venvPath = "D:\Sm_AICoder\venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "가상환경 생성: $venvPath"
    python -m venv $venvPath
} else {
    Write-Host "가상환경 이미 존재: $venvPath"
}

# 패키지 설치
$pip = "$venvPath\Scripts\pip.exe"
Write-Host "패키지 설치 중..."
& $pip install --upgrade pip
& $pip install -r requirements.txt

Write-Host ""
Write-Host "=== 설치 완료 ===" -ForegroundColor Green
Write-Host "다음 단계:"
Write-Host "  1. 모델 다운로드: D:\Sm_AICoder\venv\Scripts\python.exe scripts\download_model.py"
Write-Host "  2. 서버 시작:     .\start_server.ps1"
Write-Host "  3. 클라이언트:    .\start_client.ps1"
