# wrapper.ps1 - 봇 프로세스 관리
# exit code에 따라 재시작/업데이트 처리

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime
$soyoungRoot = Split-Path -Parent $runtimeDir  # soyoung_root
$workspaceDir = Join-Path $soyoungRoot "slackbot_workspace"

# 작업 폴더가 없으면 생성
if (-not (Test-Path $workspaceDir)) {
    New-Item -ItemType Directory -Path $workspaceDir -Force | Out-Null
    Write-Host "wrapper: 작업 폴더 생성: $workspaceDir" -ForegroundColor Yellow
}

# 작업 폴더로 이동 (Claude Code가 이 폴더에서 작업)
Set-Location $workspaceDir

# 환경 변수 설정
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $runtimeDir "src"

Write-Host "wrapper: 봇 프로세스 관리 시작" -ForegroundColor Cyan
Write-Host "wrapper: 작업 폴더: $workspaceDir" -ForegroundColor Cyan
Write-Host "wrapper: 런타임 폴더: $runtimeDir" -ForegroundColor Cyan

$pythonExe = Join-Path $runtimeDir "venv\Scripts\python.exe"

while ($true) {
    Write-Host "wrapper: 봇 시작..." -ForegroundColor Green

    $process = Start-Process -FilePath $pythonExe `
        -ArgumentList "-m", "seosoyoung.main" `
        -NoNewWindow -Wait -PassThru

    $exitCode = $process.ExitCode
    Write-Host "wrapper: 봇 종료 (exit code: $exitCode)" -ForegroundColor Yellow

    switch ($exitCode) {
        0 {
            Write-Host "wrapper: 정상 종료" -ForegroundColor Green
            break
        }
        42 {
            Write-Host "wrapper: 업데이트 요청 - git pull 실행" -ForegroundColor Cyan
            Push-Location $runtimeDir
            git pull origin main
            Pop-Location
            Write-Host "wrapper: 업데이트 완료, 재시작..." -ForegroundColor Cyan
        }
        43 {
            Write-Host "wrapper: 재시작 요청" -ForegroundColor Cyan
        }
        default {
            Write-Host "wrapper: 비정상 종료, 5초 후 재시작..." -ForegroundColor Red
            Start-Sleep -Seconds 5
        }
    }

    if ($exitCode -eq 0) { break }
}

Write-Host "wrapper: 종료" -ForegroundColor Cyan
