# start.ps1 - 봇 시작
# git pull 후 wrapper.ps1 실행

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

Set-Location $rootDir

Write-Host "start: 최신 코드 가져오는 중..." -ForegroundColor Cyan
git pull origin main

Write-Host "start: wrapper 실행" -ForegroundColor Cyan
& "$scriptDir\wrapper.ps1"
