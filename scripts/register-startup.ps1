# register-startup.ps1 - Windows 작업 스케줄러에 봇 자동 시작 등록
# 관리자 권한 필요

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"

# 작업 이름
$TaskName = "seosoyoung-bot"

# 경로 설정
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime
$startScript = Join-Path $scriptDir "start.ps1"

# 관리자 권한 확인
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] 관리자 권한이 필요합니다. PowerShell을 관리자 권한으로 실행해주세요." -ForegroundColor Red
    exit 1
}

# 기존 작업이 있는지 확인
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] 기존 작업 '$TaskName'이(가) 존재합니다. 삭제 후 재등록합니다." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# 트리거: 시스템 시작 시, 1분 지연 (네트워크 연결 대기)
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Trigger.Delay = "PT1M"  # 1분 지연

# 동작: PowerShell로 start.ps1 실행
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$startScript`"" `
    -WorkingDirectory $runtimeDir

# 설정: 네트워크 연결 대기, 무기한 실행
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Days 0)  # 무기한 실행

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
Write-Host " 작업 스케줄러 등록 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[작업 이름] $TaskName" -ForegroundColor White
Write-Host "[트리거] 시스템 시작 시 (1분 지연)" -ForegroundColor White
Write-Host "[실행 스크립트] $startScript" -ForegroundColor White
Write-Host "[실행 계정] $env:USERNAME (로그인 필요)" -ForegroundColor White
Write-Host ""
Write-Host "[수동 테스트]" -ForegroundColor Yellow
Write-Host "  schtasks /run /tn `"$TaskName`"" -ForegroundColor Gray
Write-Host ""
Write-Host "[등록 해제]" -ForegroundColor Yellow
Write-Host "  schtasks /delete /tn `"$TaskName`" /f" -ForegroundColor Gray
Write-Host ""
