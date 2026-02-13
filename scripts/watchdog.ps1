# watchdog.ps1 - supervisor 감시 스크립트
# 지수적 백오프, 자동 롤백, Claude Code 비상 복구를 지원한다.

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# ============================================================
# 경로 설정
# ============================================================

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime
$devCloneDir = Join-Path (Split-Path -Parent $runtimeDir) "slackbot_workspace\seosoyoung"
$workspaceDir = Join-Path (Split-Path -Parent $runtimeDir) "slackbot_workspace"

$python = Join-Path $runtimeDir "venv\Scripts\python.exe"
$pip = Join-Path $runtimeDir "venv\Scripts\pip.exe"

$stateFile = Join-Path $runtimeDir "data\watchdog_state.json"
$configFile = Join-Path $runtimeDir "data\watchdog_config.json"
$logsDir = Join-Path $runtimeDir "logs"

Set-Location $runtimeDir
$env:PYTHONPATH = Join-Path $runtimeDir "src"
$env:PYTHONUTF8 = "1"

# Claude Code 세션에서 watchdog이 시작된 경우, CLAUDECODE 환경변수를 제거하여
# 봇이 생성하는 CLI 세션이 중첩 세션으로 거부되는 것을 방지
Remove-Item Env:CLAUDECODE -ErrorAction SilentlyContinue

# ============================================================
# 상수
# ============================================================

$STABILITY_THRESHOLD = 60   # 초 — 이 이상 가동하면 "안정"으로 판단
$BASE_DELAY = 5             # 백오프 기본 대기(초)
$MAX_DELAY = 300            # 백오프 상한(초, 5분)
$ROLLBACK_TRIGGER = 3       # 연속 빠른 크래시 N회 → 롤백
$MAX_POST_ROLLBACK = 10     # 롤백 후 최대 재시도 횟수
$MAX_ABSOLUTE_FAILURES = 30 # 절대 최대 재시도 (롤백 여부 무관)

# ============================================================
# 설정 로드 (시작 시 1회)
# ============================================================

function Read-WatchdogConfig {
    if (-not (Test-Path $configFile)) { return $null }
    try {
        $json = Get-Content -Path $configFile -Raw -Encoding UTF8
        return ($json | ConvertFrom-Json)
    } catch {
        return $null
    }
}

$script:config = Read-WatchdogConfig

# ============================================================
# 유틸리티 함수
# ============================================================

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [watchdog] $msg"
    Write-Host $line
    $logPath = Join-Path $logsDir "watchdog.log"
    try { Add-Content -Path $logPath -Value $line -Encoding UTF8 } catch {}
}

function Get-DefaultState {
    return @{
        version             = 1
        knownGoodCommit     = @{ runtime = $null; devClone = $null }
        lastUpdateCommit    = @{ runtime = $null; devClone = $null }
        consecutiveFailures = 0
        rolledBack          = $false
        lastExitCode        = $null
        emergencyPid        = $null
    }
}

function Read-WatchdogState {
    if (-not (Test-Path $stateFile)) { return Get-DefaultState }
    try {
        $json = Get-Content -Path $stateFile -Raw -Encoding UTF8
        $obj = $json | ConvertFrom-Json
        return @{
            version             = if ($obj.version) { $obj.version } else { 1 }
            knownGoodCommit     = @{
                runtime  = $obj.knownGoodCommit.runtime
                devClone = $obj.knownGoodCommit.devClone
            }
            lastUpdateCommit    = @{
                runtime  = $obj.lastUpdateCommit.runtime
                devClone = $obj.lastUpdateCommit.devClone
            }
            consecutiveFailures = [int]$obj.consecutiveFailures
            rolledBack          = [bool]$obj.rolledBack
            lastExitCode        = $obj.lastExitCode
            emergencyPid        = $obj.emergencyPid
        }
    } catch {
        Write-Log "상태 파일 손상, 기본값으로 초기화: $_"
        return Get-DefaultState
    }
}

function Save-WatchdogState($state) {
    $dir = Split-Path -Parent $stateFile
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $json = $state | ConvertTo-Json -Depth 3
    $tmpFile = "$stateFile.tmp"
    [System.IO.File]::WriteAllText($tmpFile, $json, [System.Text.UTF8Encoding]::new($true))
    Move-Item -Path $tmpFile -Destination $stateFile -Force
}

function Get-CurrentCommits {
    $rc = (git -C $runtimeDir rev-parse HEAD 2>$null)
    $dc = (git -C $devCloneDir rev-parse HEAD 2>$null)
    return @{ runtime = $rc; devClone = $dc }
}

function Get-BackoffDelay($failures) {
    $delay = $BASE_DELAY * [Math]::Pow(2, [Math]::Max(0, $failures - 1))
    return [int][Math]::Min($delay, $MAX_DELAY)
}

function Test-ValidCommit($repoDir, $hash) {
    if (-not $hash) { return $false }
    $type = (git -C $repoDir cat-file -t $hash 2>$null)
    return ($type -eq "commit")
}

# ============================================================
# 업데이트 변경 이력
# ============================================================

function Get-UpdateChangeLog($beforeCommits, $afterCommits) {
    $lines = @(":rocket: *서소영 업데이트*")

    # seosoyoung (devClone) 이력
    if ($beforeCommits.devClone -and $afterCommits.devClone -and ($beforeCommits.devClone -ne $afterCommits.devClone)) {
        $log = (git -C $devCloneDir log --oneline --no-decorate "$($beforeCommits.devClone)..$($afterCommits.devClone)" 2>$null)
        if ($log) {
            $lines += ""
            $lines += "*seosoyoung*"
            foreach ($entry in ($log -split "`n" | Select-Object -First 10)) {
                $entry = $entry.Trim()
                if ($entry) {
                        $hash = $entry.Substring(0, [Math]::Min(7, $entry.Length))
                        $msg = if ($entry.Length -gt 8) { $entry.Substring(8) } else { "" }
                        $lines += "``$hash`` $msg"
                    }
            }
            $total = ($log -split "`n").Count
            if ($total -gt 10) { $lines += "... 외 $($total - 10)건" }
        }
    }

    # runtime 이력
    if ($beforeCommits.runtime -and $afterCommits.runtime -and ($beforeCommits.runtime -ne $afterCommits.runtime)) {
        $log = (git -C $runtimeDir log --oneline --no-decorate "$($beforeCommits.runtime)..$($afterCommits.runtime)" 2>$null)
        if ($log) {
            $lines += ""
            $lines += "*runtime*"
            foreach ($entry in ($log -split "`n" | Select-Object -First 10)) {
                $entry = $entry.Trim()
                if ($entry) {
                        $hash = $entry.Substring(0, [Math]::Min(7, $entry.Length))
                        $msg = if ($entry.Length -gt 8) { $entry.Substring(8) } else { "" }
                        $lines += "``$hash`` $msg"
                    }
            }
            $total = ($log -split "`n").Count
            if ($total -gt 10) { $lines += "... 외 $($total - 10)건" }
        }
    }

    # 변경 내역이 없으면 null 반환
    if ($lines.Count -le 1) { return $null }

    $lines += ""
    $lines += ":white_check_mark: 재시작 중..."
    return ($lines -join "`n")
}

# ============================================================
# Slack 웹훅
# ============================================================

function Send-SlackNotification($message) {
    if (-not $script:config -or -not $script:config.slackWebhookUrl) {
        Write-Log "Slack 웹훅 미설정, 알림 생략"
        return
    }
    try {
        $body = @{ text = $message } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $script:config.slackWebhookUrl -Method Post `
            -Body ([System.Text.Encoding]::UTF8.GetBytes($body)) `
            -ContentType "application/json; charset=utf-8" -TimeoutSec 10
        Write-Log "Slack 알림 전송 완료"
    } catch {
        Write-Log "Slack 알림 전송 실패: $_"
    }
}

# ============================================================
# 롤백 판단 및 실행
# ============================================================

function Test-ShouldRollback($state) {
    if ($state.consecutiveFailures -lt $ROLLBACK_TRIGGER) { return $false }
    if ($state.rolledBack -eq $true) { return $false }
    if (-not $state.knownGoodCommit.runtime) { return $false }
    # lastUpdateCommit이 기록되지 않았으면 업데이트 이력 없음 → 롤백 불가
    if (-not $state.lastUpdateCommit.runtime) { return $false }
    # 업데이트 이후 변경이 없으면 롤백 의미 없음
    if ($state.lastUpdateCommit.runtime -eq $state.knownGoodCommit.runtime -and
        $state.lastUpdateCommit.devClone -eq $state.knownGoodCommit.devClone) { return $false }
    return $true
}

function Invoke-Rollback($state) {
    Write-Log "=== 롤백 실행 ==="
    Write-Log "  runtime  -> $($state.knownGoodCommit.runtime)"
    Write-Log "  devClone -> $($state.knownGoodCommit.devClone)"

    # 커밋 해시 검증
    if (-not (Test-ValidCommit $runtimeDir $state.knownGoodCommit.runtime)) {
        Write-Log "유효하지 않은 runtime 커밋 해시, 롤백 중단"
        Send-SlackNotification ":x: 롤백 실패: 유효하지 않은 runtime 커밋 해시 ``$($state.knownGoodCommit.runtime)``"
        return $false
    }
    if (-not (Test-ValidCommit $devCloneDir $state.knownGoodCommit.devClone)) {
        Write-Log "유효하지 않은 devClone 커밋 해시, 롤백 중단"
        Send-SlackNotification ":x: 롤백 실패: 유효하지 않은 devClone 커밋 해시 ``$($state.knownGoodCommit.devClone)``"
        return $false
    }

    # Slack 알림: 롤백 시작
    $msg = @"
:rotating_light: *supervisor 비상 롤백 실행*
연속 크래시 $($state.consecutiveFailures)회 감지. 안정 버전으로 롤백합니다.
- 크래시 커밋(runtime): ``$($state.lastUpdateCommit.runtime)``
- 크래시 커밋(devClone): ``$($state.lastUpdateCommit.devClone)``
- 롤백 대상(runtime): ``$($state.knownGoodCommit.runtime)``
- 롤백 대상(devClone): ``$($state.knownGoodCommit.devClone)``
Claude Code 비상 복구 모드를 시작합니다.
"@
    Send-SlackNotification $msg

    # runtime 롤백
    git -C $runtimeDir reset --hard $state.knownGoodCommit.runtime
    $runtimeOk = ($LASTEXITCODE -eq 0)

    $pipLog = Join-Path $logsDir "pip_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
    & $pip install -r (Join-Path $runtimeDir "requirements.txt") --quiet 2>&1 | Out-File -Append $pipLog
    if ($LASTEXITCODE -ne 0) { Write-Log "pip install 실패, 로그: $pipLog" }

    # devClone 롤백
    git -C $devCloneDir reset --hard $state.knownGoodCommit.devClone
    $devCloneOk = ($LASTEXITCODE -eq 0)

    if (-not $runtimeOk -or -not $devCloneOk) {
        Write-Log "롤백 부분 실패: runtime=$runtimeOk, devClone=$devCloneOk"
        Send-SlackNotification ":x: 롤백 부분 실패 (runtime=$runtimeOk, devClone=$devCloneOk). 수동 개입 필요."
        return $false
    }

    # 상태 갱신
    $state.rolledBack = $true
    $state.consecutiveFailures = 0
    Save-WatchdogState $state

    # Claude Code 비상 복구 실행
    Invoke-EmergencyRecovery $state

    Write-Log "롤백 완료, 즉시 재시작"
    return $true
}

# ============================================================
# Claude Code 비상 복구
# ============================================================

function Invoke-EmergencyRecovery($state) {
    # 기존 비상 복구 프로세스 확인
    if ($state.emergencyPid) {
        $existing = Get-Process -Id $state.emergencyPid -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Log "기존 비상 복구 프로세스 실행 중 (PID: $($state.emergencyPid)), 중복 실행 생략"
            return
        }
    }

    Write-Log "Claude Code 비상 복구 모드 시작"

    $prompt = @"
[비상 복구 모드] supervisor가 연속 크래시로 자동 롤백되었습니다.

상황:
- 크래시 커밋(runtime): $($state.lastUpdateCommit.runtime)
- 크래시 커밋(devClone): $($state.lastUpdateCommit.devClone)
- 롤백된 안정 커밋(runtime): $($state.knownGoodCommit.runtime)
- 롤백된 안정 커밋(devClone): $($state.knownGoodCommit.devClone)
- 마지막 Exit code: $($state.lastExitCode)

작업 지시:
1. 크래시를 유발한 커밋들을 분석하세요 (git log, git diff 활용).
2. 문제의 원인을 파악하고 seosoyoung 리포에서 수정하세요.
3. 수정 사항을 커밋하고 push하세요.
4. seosoyoung_runtime에서 git pull 후 supervisor를 직접 실행하여 60초 이상 정상 가동되는지 확인하세요.
   - 실행 명령: python -m supervisor (cwd: seosoyoung_runtime, PYTHONPATH=src, PYTHONUTF8=1)
   - 60초 이상 에러 없이 가동되면 정상으로 판단합니다.
   - 정상 확인 후 supervisor를 종료하세요 (watchdog가 자체적으로 재시작합니다).
5. 완료 후 Slack 웹훅으로 결과를 보고하세요.
   - 설정 파일에서 웹훅 URL을 읽으세요: $configFile
   - JSON 형식으로 slackWebhookUrl 키를 읽어서 POST하면 됩니다.
   - 보고 내용: 원인 분석, 수정 내용, 커밋 해시, supervisor 정상 가동 확인 여부.
"@

    # 프롬프트를 파일에 저장 (PowerShell 인자 이스케이프 문제 회피)
    $promptFile = Join-Path $runtimeDir "data\emergency_prompt.txt"
    [System.IO.File]::WriteAllText($promptFile, $prompt, [System.Text.UTF8Encoding]::new($false))

    $logFile = Join-Path $logsDir "emergency_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

    try {
        $cmd = "Get-Content -Path '$promptFile' -Raw | claude -p --dangerously-skip-permissions *> '$logFile'"
        $proc = Start-Process powershell `
            -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd `
            -WorkingDirectory $workspaceDir -PassThru
        $state.emergencyPid = $proc.Id
        Save-WatchdogState $state
        Write-Log "Claude Code 비상 복구 프로세스 시작됨 (PID: $($proc.Id), 로그: $logFile)"
    } catch {
        Write-Log "Claude Code 실행 실패: $_"
        Send-SlackNotification ":warning: Claude Code 비상 복구 모드 실행 실패: $_"
    }
}

# ============================================================
# 메인 루프
# ============================================================

Write-Log "supervisor 감시 시작"

$state = Read-WatchdogState
Write-Log "초기 상태: failures=$($state.consecutiveFailures), rolledBack=$($state.rolledBack)"

while ($true) {
    $startTime = Get-Date
    $currentCommits = Get-CurrentCommits

    Write-Log "supervisor 시작"
    & $python -m supervisor
    $exitCode = $LASTEXITCODE
    $state.lastExitCode = $exitCode

    $uptime = ((Get-Date) - $startTime).TotalSeconds
    Write-Log "supervisor 종료: exit=$exitCode, uptime=$([Math]::Round($uptime, 1))s"

    # --- Exit 0: 정상 종료 ---
    if ($exitCode -eq 0) {
        Write-Log "정상 종료, 루프 탈출"
        $state.consecutiveFailures = 0
        Save-WatchdogState $state
        break
    }

    # --- Exit 42: 코드 변경 → git pull + pip install → 즉시 재시작 ---
    if ($exitCode -eq 42) {
        Write-Log "코드 변경 감지, 업데이트 중..."
        $beforeCommits = Get-CurrentCommits

        git -C $runtimeDir pull origin main
        if ($LASTEXITCODE -ne 0) {
            Write-Log "runtime git pull 실패, 이전 상태로 재시작"
            Send-SlackNotification ":warning: runtime git pull 실패. 수동 확인 필요."
            Start-Sleep -Seconds $BASE_DELAY
            continue
        }

        $pipLog = Join-Path $logsDir "pip_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
        & $pip install -r (Join-Path $runtimeDir "requirements.txt") --quiet 2>&1 | Out-File -Append $pipLog
        if ($LASTEXITCODE -ne 0) { Write-Log "pip install 실패, 로그: $pipLog" }

        git -C $devCloneDir pull origin main
        if ($LASTEXITCODE -ne 0) {
            Write-Log "devClone git pull 실패 (비치명적, 계속 진행)"
        }

        $state.lastUpdateCommit = Get-CurrentCommits
        $state.consecutiveFailures = 0
        $state.rolledBack = $false
        Save-WatchdogState $state

        # 업데이트 내역을 Slack 웹훅으로 전송
        $changeLog = Get-UpdateChangeLog $beforeCommits $state.lastUpdateCommit
        if ($changeLog) {
            Send-SlackNotification $changeLog
        }

        Write-Log "업데이트 완료, 즉시 재시작"
        continue
    }

    # --- Exit 43: 재시작 요청 ---
    if ($exitCode -eq 43) {
        Write-Log "재시작 요청 수신, 즉시 재시작"
        $state.consecutiveFailures = 0
        Save-WatchdogState $state
        continue
    }

    # --- 비정상 종료: 안정성 판단 ---
    if ($uptime -ge $STABILITY_THRESHOLD) {
        # 충분히 돌다가 크래시 → 일시적 장애
        Write-Log "안정 실행 후 크래시 (uptime: $([Math]::Round($uptime, 1))s), 일시적 장애로 판단"
        $state.knownGoodCommit = $currentCommits
        $state.consecutiveFailures = 0
        $state.rolledBack = $false
        Save-WatchdogState $state
    } else {
        # 빠른 크래시 → 연속 실패
        $state.consecutiveFailures++
        Write-Log "빠른 크래시 (uptime: $([Math]::Round($uptime, 1))s), 연속 실패: $($state.consecutiveFailures)"
        Save-WatchdogState $state
    }

    # --- 롤백 판단 ---
    if (Test-ShouldRollback $state) {
        $rollbackOk = Invoke-Rollback $state
        if ($rollbackOk) {
            continue  # 롤백 성공 → 즉시 재시작
        }
        # 롤백 실패 → 백오프로 진행
    }

    # --- circuit breaker ---
    # 롤백 후 반복 실패
    if ($state.rolledBack -and $state.consecutiveFailures -ge $ROLLBACK_TRIGGER) {
        if ($state.consecutiveFailures -eq $ROLLBACK_TRIGGER) {
            Send-SlackNotification ":warning: 롤백 후에도 supervisor 크래시 지속. 수동 개입이 필요합니다."
        }
        if ($state.consecutiveFailures -ge $MAX_POST_ROLLBACK) {
            Write-Log "최대 재시도 횟수($MAX_POST_ROLLBACK) 초과, 감시 종료"
            Send-SlackNotification ":skull: watchdog 최대 재시도 초과. 감시를 종료합니다. 수동 개입이 필요합니다."
            break
        }
    }
    # 절대 최대 재시도 (롤백 여부 무관)
    if ($state.consecutiveFailures -ge $MAX_ABSOLUTE_FAILURES) {
        Write-Log "절대 최대 재시도($MAX_ABSOLUTE_FAILURES) 초과, 감시 종료"
        Send-SlackNotification ":skull: supervisor 연속 크래시 $($state.consecutiveFailures)회. 롤백 불가 상태에서 최대 재시도 초과. 수동 개입이 필요합니다."
        break
    }

    # --- 지수적 백오프 대기 ---
    $delay = Get-BackoffDelay $state.consecutiveFailures
    Write-Log "${delay}초 후 재시작..."
    Start-Sleep -Seconds $delay
}

Write-Log "감시 종료"
