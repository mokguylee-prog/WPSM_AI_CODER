$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverDir = Split-Path -Parent $scriptDir
$projectRoot = Split-Path -Parent $serverDir

$driveRoot = "D:\Sm_AICoder"
$cacheDir = Join-Path $driveRoot "hf_cache"
$pipCacheDir = Join-Path $driveRoot "pip_cache"
$modelStorageDir = Join-Path $driveRoot "models\gguf"

$projectModelParent = Join-Path $projectRoot "Sm_AICoder\models"
$projectModelDir = Join-Path $projectModelParent "gguf"
$projectVenvDir = Join-Path $projectRoot "venv"
$projectPython = Join-Path $projectVenvDir "Scripts\python.exe"
$requirementsFile = Join-Path $projectRoot "requirements.txt"

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Test-ReparsePoint {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $item = Get-Item -LiteralPath $Path -Force
    return [bool]($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
}

function Ensure-ModelDirectory {
    Ensure-Directory $projectModelParent

    if (-not (Test-Path -LiteralPath $projectModelDir)) {
        New-Item -ItemType Junction -Path $projectModelDir -Target $modelStorageDir | Out-Null
        Write-Host "Project model directory linked to D drive:" -ForegroundColor Green
        Write-Host "  $projectModelDir -> $modelStorageDir"
        return
    }

    if (Test-ReparsePoint $projectModelDir) {
        Write-Host "Existing model link preserved: $projectModelDir" -ForegroundColor Yellow
        return
    }

    $children = @(Get-ChildItem -LiteralPath $projectModelDir -Force -ErrorAction SilentlyContinue)
    if ($children.Count -eq 0) {
        Remove-Item -LiteralPath $projectModelDir -Force
        New-Item -ItemType Junction -Path $projectModelDir -Target $modelStorageDir | Out-Null
        Write-Host "Empty project model directory replaced with D drive link." -ForegroundColor Green
        Write-Host "  $projectModelDir -> $modelStorageDir"
        return
    }

    Write-Host "Project model directory already has files, leaving it unchanged:" -ForegroundColor Yellow
    Write-Host "  $projectModelDir"
    Write-Host "Move the GGUF files to $modelStorageDir manually if you want them stored on D drive."
}

Write-Host "=== Sm_AICoder D drive setup ===" -ForegroundColor Cyan
Write-Host "Project root: $projectRoot"

Ensure-Directory $driveRoot
Ensure-Directory $cacheDir
Ensure-Directory $pipCacheDir
Ensure-Directory $modelStorageDir

[System.Environment]::SetEnvironmentVariable("HF_HOME", $cacheDir, "User")
[System.Environment]::SetEnvironmentVariable("TRANSFORMERS_CACHE", $cacheDir, "User")
[System.Environment]::SetEnvironmentVariable("PIP_CACHE_DIR", $pipCacheDir, "User")
$env:HF_HOME = $cacheDir
$env:TRANSFORMERS_CACHE = $cacheDir
$env:PIP_CACHE_DIR = $pipCacheDir

Write-Host "Cache environment variables configured." -ForegroundColor Green
Write-Host "  HF_HOME            = $cacheDir"
Write-Host "  TRANSFORMERS_CACHE = $cacheDir"
Write-Host "  PIP_CACHE_DIR      = $pipCacheDir"

Ensure-ModelDirectory

if (-not (Test-Path -LiteralPath $projectPython)) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        throw "python command not found. Install Python 3.10~3.13 first."
    }

    Write-Host "Creating project virtual environment: $projectVenvDir"
    & $pythonCmd.Path -m venv $projectVenvDir
} else {
    Write-Host "Project virtual environment already exists: $projectVenvDir"
}

Write-Host "Installing packages into project venv..." -ForegroundColor Cyan
& $projectPython -m pip install --upgrade pip
& $projectPython -m pip install -r $requirementsFile

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "This script keeps launcher compatibility by using the project-root venv."
Write-Host "If the model path was linked successfully, GGUF files will be stored on D drive."
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Model download: venv\Scripts\python.exe server\scripts\download_model.py"
Write-Host "  2. Start server:   .\start_server.ps1"
Write-Host "  3. Start GUI:      .\start_gui.ps1"
Write-Host "  4. Start CLI:      .\start_client.ps1"
