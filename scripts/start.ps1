# start.ps1 - 봇 시작
# git pull 후 wrapper.ps1 실행

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime

Set-Location $runtimeDir

Write-Host "start: 최신 코드 가져오는 중..." -ForegroundColor Cyan
git pull origin main

# 의존성 설치
$pipExe = Join-Path $runtimeDir "venv\Scripts\pip.exe"
$requirementsFile = Join-Path $runtimeDir "requirements.txt"
if (Test-Path $requirementsFile) {
    Write-Host "start: 의존성 설치 중..." -ForegroundColor Cyan
    & $pipExe install -r $requirementsFile --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "start: 의존성 설치 완료" -ForegroundColor Green
    } else {
        Write-Host "start: 의존성 설치 실패 (계속 진행)" -ForegroundColor Yellow
    }
}

Write-Host "start: wrapper 실행" -ForegroundColor Cyan
& "$scriptDir\wrapper.ps1"
