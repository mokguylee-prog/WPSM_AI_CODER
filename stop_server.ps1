chcp 65001 | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pidFile = Join-Path $scriptDir "server\server.pid"
$port = 8888

function Get-ListenerPid {
    param([int]$TargetPort)

    $line = netstat -ano | Select-String "0.0.0.0:$TargetPort\s+0.0.0.0:0\s+LISTENING" | Select-Object -First 1
    if ($line) {
        $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
        if ($parts.Count -gt 0) {
            return [int]$parts[-1]
        }
    }

    return $null
}

$targetPids = @()

if (Test-Path $pidFile) {
    $raw = Get-Content $pidFile -Raw
    $matches = [regex]::Matches($raw, "\d+")
    foreach ($m in $matches) {
        $targetPids += [int]$m.Value
    }
}

$listenerPid = Get-ListenerPid -TargetPort $port
if ($listenerPid) {
    $targetPids += $listenerPid
}

$targetPids = $targetPids | Sort-Object -Unique

if (-not $targetPids -or $targetPids.Count -eq 0) {
    Write-Host "종료할 서버 PID를 찾지 못했습니다. (port:$port)"
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -ErrorAction SilentlyContinue
        Write-Host "stale server.pid 삭제 완료"
    }
    exit
}

foreach ($targetPid in $targetPids) {
    Write-Host "종료 시도 중... (PID: $targetPid)"
    $result = taskkill /PID $targetPid /T /F 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "종료 완료 (PID: $targetPid)"
    } else {
        Write-Host "이미 종료되었거나 찾을 수 없음 (PID: $targetPid)"
    }
}

if (Test-Path $pidFile) {
    Remove-Item $pidFile -ErrorAction SilentlyContinue
    Write-Host "server.pid 삭제 완료"
}

Start-Sleep -Milliseconds 500
$remainingListener = Get-ListenerPid -TargetPort $port
if ($remainingListener) {
    Write-Host "경고: 포트 $port 리스너가 아직 남아 있습니다. (PID: $remainingListener)"
} else {
    Write-Host "포트 $port 리스너 종료 확인 완료"
}
