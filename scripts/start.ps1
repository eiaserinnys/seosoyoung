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

Write-Host "start: wrapper 실행" -ForegroundColor Cyan
& "$scriptDir\wrapper.ps1"
