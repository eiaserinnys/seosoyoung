# install-service.ps1 - Task Scheduler에 supervisor watchdog 서비스 등록
# 관리자 권한 필요. register-startup.ps1을 대체.

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"

# 작업 이름
$TaskName = "seosoyoung-supervisor"

# 경로 설정
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime
$watchdogScript = Join-Path $scriptDir "watchdog.ps1"

# watchdog.ps1 존재 확인
if (-not (Test-Path $watchdogScript)) {
    Write-Host "[ERROR] watchdog.ps1을 찾을 수 없습니다: $watchdogScript" -ForegroundColor Red
    exit 1
}

# 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] 관리자 권한이 필요합니다. PowerShell을 관리자 권한으로 실행해주세요." -ForegroundColor Red
    exit 1
}

# 기존 작업 정리 (이전 register-startup.ps1의 작업 포함)
$oldTaskNames = @("seosoyoung-bot", $TaskName)
foreach ($name in $oldTaskNames) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[INFO] 기존 작업 '$name' 삭제" -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}

# 트리거: 시스템 시작 시, 1분 지연 (네트워크 연결 대기)
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Trigger.Delay = "PT1M"

# 동작: PowerShell -WindowStyle Hidden으로 watchdog.ps1 실행
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$watchdogScript`"" `
    -WorkingDirectory $runtimeDir

# 설정: 무기한 실행, 배터리에서도 실행
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)

# 현재 사용자로 실행 (로그인 필요)
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

# 작업 등록
$Task = New-ScheduledTask -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal
Register-ScheduledTask -TaskName $TaskName -InputObject $Task | Out-Null

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 서비스 등록 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[작업 이름] $TaskName" -ForegroundColor White
Write-Host "[트리거] 시스템 시작 시 (1분 지연)" -ForegroundColor White
Write-Host "[실행 대상] watchdog.ps1 (WindowStyle Hidden)" -ForegroundColor White
Write-Host "[실행 계정] $env:USERNAME (로그인 필요)" -ForegroundColor White
Write-Host ""
Write-Host "[수동 테스트]" -ForegroundColor Yellow
Write-Host "  schtasks /run /tn `"$TaskName`"" -ForegroundColor Gray
Write-Host ""
Write-Host "[등록 해제]" -ForegroundColor Yellow
Write-Host "  schtasks /delete /tn `"$TaskName`" /f" -ForegroundColor Gray
Write-Host ""
