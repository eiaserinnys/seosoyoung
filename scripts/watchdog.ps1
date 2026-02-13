# watchdog.ps1 - supervisor를 감싸는 최소한의 루프
# supervisor 자체 업데이트를 해결하기 위한 스크립트.
# 복잡한 로직은 전부 supervisor 쪽에 있으므로 이 파일은 거의 변경할 일이 없다.

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime
$pythonw = Join-Path $runtimeDir "venv\Scripts\pythonw.exe"

Set-Location $runtimeDir
$env:PYTHONPATH = Join-Path $runtimeDir "src"
$env:PYTHONUTF8 = "1"

while ($true) {
    & $pythonw -m supervisor
    $code = $LASTEXITCODE

    if ($code -eq 0) {
        # 정상 종료 → 루프 탈출
        break
    }

    if ($code -eq 42) {
        # supervisor 자체 코드 변경 → pull 후 재시작
        git pull origin main
    }

    # 그 외 비정상 종료 → 5초 후 재시작
    Start-Sleep -Seconds 5
}
