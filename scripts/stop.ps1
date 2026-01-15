# stop.ps1 - 봇 종료
# seosoyoung.main 프로세스와 자식 프로세스 모두 종료

$ErrorActionPreference = "SilentlyContinue"

Write-Host "stop: seosoyoung 봇 프로세스 검색 중..." -ForegroundColor Cyan

$processes = Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*seosoyoung.main*"
}

if ($processes) {
    foreach ($proc in $processes) {
        Write-Host "stop: PID $($proc.ProcessId) 및 자식 프로세스 종료" -ForegroundColor Yellow
        # /T: 자식 프로세스도 종료, /F: 강제 종료
        taskkill /PID $proc.ProcessId /T /F 2>$null
    }
    Write-Host "stop: 봇 종료 완료" -ForegroundColor Green
} else {
    Write-Host "stop: 실행 중인 봇 프로세스 없음" -ForegroundColor Yellow
}
