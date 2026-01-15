# stop.ps1 - 봇 종료
# seosoyoung.main 프로세스 찾아서 종료

$ErrorActionPreference = "SilentlyContinue"

Write-Host "stop: seosoyoung 봇 프로세스 검색 중..." -ForegroundColor Cyan

$processes = Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like "*seosoyoung.main*"
}

if ($processes) {
    foreach ($proc in $processes) {
        Write-Host "stop: PID $($proc.ProcessId) 종료" -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force
    }
    Write-Host "stop: 봇 종료 완료" -ForegroundColor Green
} else {
    Write-Host "stop: 실행 중인 봇 프로세스 없음" -ForegroundColor Yellow
}
