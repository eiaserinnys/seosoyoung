# install-service.ps1 - NSSM으로 watchdog을 Windows 서비스로 등록
# 관리자 권한 PowerShell에서 실행해야 합니다.

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Continue"

$serviceName = "SeoSoyoungWatchdog"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir
$logsDir = Join-Path $runtimeDir "logs"
$watchdogScript = Join-Path $scriptDir "watchdog.ps1"

# NSSM 찾기
$nssm = Get-Command nssm -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $nssm) {
    $nssm = "C:\Users\LG\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe"
}
if (-not (Test-Path $nssm)) {
    Write-Host "[ERROR] NSSM을 찾을 수 없습니다. winget install nssm 으로 설치해주세요." -ForegroundColor Red
    exit 1
}

# 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] 관리자 권한이 필요합니다. PowerShell을 관리자 권한으로 실행해주세요." -ForegroundColor Red
    exit 1
}

# watchdog.ps1 존재 확인
if (-not (Test-Path $watchdogScript)) {
    Write-Host "[ERROR] watchdog.ps1을 찾을 수 없습니다: $watchdogScript" -ForegroundColor Red
    exit 1
}

# 기존 서비스 정리
$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[INFO] 기존 서비스 '$serviceName' 제거 중..." -ForegroundColor Yellow
    $ErrorActionPreference = "SilentlyContinue"
    & $nssm stop $serviceName *>&1 | Out-Null
    & $nssm remove $serviceName confirm *>&1 | Out-Null
    $ErrorActionPreference = "Continue"
    Start-Sleep -Seconds 2
}

# 기존 Task Scheduler 작업 정리
$oldTaskNames = @("seosoyoung-bot", "seosoyoung-supervisor")
foreach ($name in $oldTaskNames) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Write-Host "[INFO] 기존 예약 작업 '$name' 삭제" -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}

Write-Host ""
Write-Host "서비스 등록 중..." -ForegroundColor Cyan

# 서비스 등록
& $nssm install $serviceName "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" `
    "-NoProfile -ExecutionPolicy Bypass -File `"$watchdogScript`""

# 서비스 설정
& $nssm set $serviceName AppDirectory $runtimeDir
& $nssm set $serviceName DisplayName "SeoSoyoung Watchdog"
& $nssm set $serviceName Description "seosoyoung 슬랙봇 supervisor 감시 서비스 (Session 0, 환경변수 격리)"
& $nssm set $serviceName Start SERVICE_AUTO_START

# 로그 설정
& $nssm set $serviceName AppStdout "$logsDir\service_stdout.log"
& $nssm set $serviceName AppStderr "$logsDir\service_stderr.log"
& $nssm set $serviceName AppRotateFiles 1
& $nssm set $serviceName AppRotateBytes 10485760

# 종료/재시작 동작 — watchdog 자체가 크래시하면 NSSM이 재시작
& $nssm set $serviceName AppExit Default Restart
& $nssm set $serviceName AppRestartDelay 5000

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 서비스 등록 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[서비스 이름] $serviceName" -ForegroundColor White
Write-Host "[실행 방식] NSSM -> PowerShell -> watchdog.ps1" -ForegroundColor White
Write-Host "[실행 환경] Session 0 (LocalSystem, 환경변수 격리)" -ForegroundColor White
Write-Host "[자동 시작] 부팅 시 자동 시작" -ForegroundColor White
Write-Host ""
Write-Host "[관리 명령]" -ForegroundColor Yellow
Write-Host "  시작:   nssm start $serviceName" -ForegroundColor Gray
Write-Host "  중지:   nssm stop $serviceName" -ForegroundColor Gray
Write-Host "  재시작: nssm restart $serviceName" -ForegroundColor Gray
Write-Host "  상태:   nssm status $serviceName" -ForegroundColor Gray
Write-Host "  제거:   nssm remove $serviceName confirm" -ForegroundColor Gray
Write-Host ""

$answer = Read-Host "지금 서비스를 시작하시겠습니까? (y/n)"
if ($answer -eq "y") {
    & $nssm start $serviceName
    Start-Sleep -Seconds 5
    $svc = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Write-Host "서비스 시작 완료! (상태: $($svc.Status))" -ForegroundColor Green
    } else {
        Write-Host "서비스 상태: $($svc.Status) — 로그를 확인해주세요: $logsDir" -ForegroundColor Yellow
    }
}
