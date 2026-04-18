chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$clientDir = Join-Path $scriptDir "client"
$venvPython = Join-Path $scriptDir "venv\Scripts\python.exe"
$venvPip = Join-Path $scriptDir "venv\Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    $venvPython = "python"
    $venvPip = "pip"
    Write-Host "[경고] 가상환경을 찾지 못했습니다. 시스템 Python을 사용합니다."
}

Push-Location $clientDir
try {
    Write-Host ""
    Write-Host "========================================"
    Write-Host " Sm_AICoder GUI Client - EXE 빌드 시작"
    Write-Host "========================================"
    Write-Host ""

    Write-Host "[1/5] 필수 패키지 확인..."
    $piCheck = & $venvPython -c "import PyInstaller" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      PyInstaller 없음 -> 설치 중..."
        & $venvPip install pyinstaller --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[오류] PyInstaller 설치 실패. 종료합니다."
            exit 1
        }
        Write-Host "      PyInstaller 설치 완료."
    } else {
        Write-Host "      PyInstaller가 이미 설치되어 있습니다."
    }

    $plCheck = & $venvPython -c "import PIL" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      Pillow 없음 -> 설치 중..."
        & $venvPip install pillow --quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[오류] Pillow 설치 실패. 종료합니다."
            exit 1
        }
        Write-Host "      Pillow 설치 완료."
    } else {
        Write-Host "      Pillow가 이미 설치되어 있습니다."
    }

    Write-Host ""
    Write-Host "[2/5] 이전 빌드 파일 정리..."
    if (Test-Path "dist\Sm_AiCoderClient.exe") {
        Remove-Item "dist\Sm_AiCoderClient.exe" -Force
        Write-Host "      dist\Sm_AiCoderClient.exe 삭제"
    }
    if (Test-Path "build") {
        Remove-Item "build" -Recurse -Force
        Write-Host "      build 폴더 삭제"
    }
    if (Test-Path "Sm_AiCoderClient.spec") {
        Remove-Item "Sm_AiCoderClient.spec" -Force
        Write-Host "      Sm_AiCoderClient.spec 삭제"
    }

    Write-Host ""
    Write-Host "[3/5] 아이콘 생성..."
    & $venvPython ".\make_icon.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      [경고] 아이콘 생성 실패 - 기본 아이콘으로 빌드합니다."
    }

    Write-Host ""
    Write-Host "[4/5] TCL/TK 경로 확인..."

    $tclTkInfo = & $venvPython -c @"
import sys, os
exe_dir = os.path.dirname(sys.executable)
base_dir = getattr(sys, 'base_prefix', exe_dir)
base_scripts = os.path.join(base_dir, 'Scripts')
candidates = [exe_dir, base_dir, base_scripts,
              os.path.dirname(exe_dir), os.path.dirname(base_dir)]
tcl = tk = ''
for base in candidates:
    t = os.path.join(base, 'tcl', 'tcl8.6')
    if not tcl and os.path.isdir(t):
        tcl = t
    t = os.path.join(base, 'tcl', 'tk8.6')
    if not tk and os.path.isdir(t):
        tk = t
print(tcl)
print(tk)
"@

    $tclPath = $tclTkInfo[0].Trim()
    $tkPath = $tclTkInfo[1].Trim()

    if ($tclPath) {
        Write-Host "      TCL: $tclPath"
    } else {
        Write-Host "      [경고] TCL 경로를 찾지 못했습니다."
    }
    if ($tkPath) {
        Write-Host "      TK : $tkPath"
    } else {
        Write-Host "      [경고] TK 경로를 찾지 못했습니다."
    }

    Write-Host ""
    Write-Host "[5/5] PyInstaller 빌드 실행 중..."
    Write-Host "      (완료까지 1~3분 정도 걸릴 수 있습니다)"
    Write-Host ""

    $buildArgs = @(
        "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "Sm_AiCoderClient",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.scrolledtext",
        "--hidden-import", "_tkinter",
        "--collect-all", "tkinter"
    )

    if (Test-Path "icon.ico") {
        $buildArgs += "--icon"
        $buildArgs += "icon.ico"
        $buildArgs += "--add-data"
        $buildArgs += "icon.ico;."
        Write-Host "      아이콘 icon.ico 적용"
    }

    if ($tclPath) {
        $buildArgs += "--add-data"
        $buildArgs += "${tclPath};_tcl_data"
    }
    if ($tkPath) {
        $buildArgs += "--add-data"
        $buildArgs += "${tkPath};_tk_data"
    }
    $buildArgs += "gui_client.py"

    & $venvPython @buildArgs

    if ($LASTEXITCODE -eq 0) {
        $dest = Join-Path $clientDir "Sm_AiCoderClient.exe"
        Copy-Item "dist\Sm_AiCoderClient.exe" -Destination $dest -Force
        Write-Host ""
        Write-Host "========================================"
        Write-Host " 빌드 성공!"
        Write-Host " 복사 완료: $dest"
        Write-Host "========================================"
        Write-Host ""
        Write-Host "[주의] exe 실행 전 api_server(서버)가 먼저 실행되어 있어야 합니다."
        Write-Host ""
        Write-Host "Sm_AiCoderClient.exe 실행 중..."
        Start-Process $dest
    } else {
        Write-Host ""
        Write-Host "[오류] 빌드 실패. 로그를 확인하세요."
        exit 1
    }
}
finally {
    Pop-Location
}
