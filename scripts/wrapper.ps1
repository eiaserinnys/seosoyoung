# wrapper.ps1 - 봇 프로세스 관리
# exit code에 따라 재시작/업데이트 처리

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

Set-Location $rootDir

# 환경 변수 설정
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "src"

Write-Host "wrapper: 봇 프로세스 관리 시작" -ForegroundColor Cyan

while ($true) {
    Write-Host "wrapper: 봇 시작..." -ForegroundColor Green

    $process = Start-Process -FilePath ".\venv\Scripts\python.exe" `
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
            git pull origin main
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
