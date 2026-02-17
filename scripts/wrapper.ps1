# wrapper.ps1 - 봇 프로세스 관리
# exit code에 따라 재시작/업데이트 처리

# UTF-8 인코딩 설정 (한국어 깨짐 방지)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runtimeDir = Split-Path -Parent $scriptDir  # seosoyoung_runtime
$soyoungRoot = Split-Path -Parent $runtimeDir  # soyoung_root
$workspaceDir = Join-Path $soyoungRoot "slackbot_workspace"

# 로그 설정
$logsDir = Join-Path $runtimeDir "logs"
if (-not (Test-Path $logsDir)) {
    New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
}
$logFile = Join-Path $logsDir "wrapper_$(Get-Date -Format 'yyyyMMdd').log"
Start-Transcript -Path $logFile -Append

# 에러 발생 시에도 계속 진행 (로그에 기록됨)
$ErrorActionPreference = "Continue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "wrapper: 시작 - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 작업 폴더가 없으면 생성
if (-not (Test-Path $workspaceDir)) {
    New-Item -ItemType Directory -Path $workspaceDir -Force | Out-Null
    Write-Host "wrapper: 작업 폴더 생성: $workspaceDir" -ForegroundColor Yellow
}

# slackbot_workspace/seosoyoung 개발용 소스 동기화 함수
function Sync-DevSeosoyoung {
    $devSeosoyoung = Join-Path $workspaceDir "seosoyoung"
    $repoUrl = "https://github.com/eias/seosoyoung"

    if (-not (Test-Path $devSeosoyoung)) {
        Write-Host "wrapper: seosoyoung 개발 소스 클론 중..." -ForegroundColor Cyan
        git clone $repoUrl $devSeosoyoung
        if ($LASTEXITCODE -eq 0) {
            Write-Host "wrapper: seosoyoung 클론 완료: $devSeosoyoung" -ForegroundColor Green
        } else {
            Write-Host "wrapper: seosoyoung 클론 실패" -ForegroundColor Red
        }
    } else {
        Write-Host "wrapper: seosoyoung 개발 소스 동기화 중..." -ForegroundColor Cyan
        Push-Location $devSeosoyoung
        git pull origin main
        if ($LASTEXITCODE -eq 0) {
            Write-Host "wrapper: seosoyoung 동기화 완료" -ForegroundColor Green
        } else {
            Write-Host "wrapper: seosoyoung 동기화 실패 (로컬 변경사항 있음?)" -ForegroundColor Yellow
        }
        Pop-Location
    }
}

# 초기 동기화
Sync-DevSeosoyoung

# 작업 폴더로 이동 (Claude Code가 이 폴더에서 작업)
Set-Location $workspaceDir

# 환경 변수 설정
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $runtimeDir "src"

# CLAUDE_CONFIG_DIR 설정 (프로필 기반)
function Set-ClaudeConfigDir {
    $profilesDir = Join-Path $workspaceDir ".local\claude_profiles"
    $activeFile = Join-Path $profilesDir "_active.txt"

    if (Test-Path $activeFile) {
        $activeName = (Get-Content -Path $activeFile -Encoding UTF8).Trim()
        if ($activeName) {
            $profileDir = Join-Path $profilesDir $activeName
            if (Test-Path $profileDir) {
                $env:CLAUDE_CONFIG_DIR = $profileDir
                Write-Host "wrapper: CLAUDE_CONFIG_DIR=$profileDir (profile: $activeName)" -ForegroundColor Green
                return
            } else {
                Write-Host "wrapper: 프로필 디렉토리 없음: $profileDir" -ForegroundColor Yellow
            }
        }
    }

    # 활성 프로필 없으면 환경변수 제거 (기본 ~/.claude 사용)
    if ($env:CLAUDE_CONFIG_DIR) {
        Remove-Item Env:CLAUDE_CONFIG_DIR -ErrorAction SilentlyContinue
    }
    Write-Host "wrapper: CLAUDE_CONFIG_DIR 미설정 (기본 경로 사용)" -ForegroundColor Yellow
}

Set-ClaudeConfigDir

Write-Host "wrapper: 봇 프로세스 관리 시작" -ForegroundColor Cyan
Write-Host "wrapper: 작업 폴더: $workspaceDir" -ForegroundColor Cyan
Write-Host "wrapper: 런타임 폴더: $runtimeDir" -ForegroundColor Cyan

$pythonExe = Join-Path $runtimeDir "venv\Scripts\python.exe"

while ($true) {
    # 매 시작 시 프로필 설정 재확인
    Set-ClaudeConfigDir

    Write-Host "wrapper: 봇 시작..." -ForegroundColor Green

    # 직접 실행 (출력이 콘솔과 로그에 캡처됨)
    & $pythonExe -m seosoyoung.main
    $exitCode = $LASTEXITCODE

    Write-Host "wrapper: 봇 종료 (exit code: $exitCode)" -ForegroundColor Yellow

    switch ($exitCode) {
        0 {
            Write-Host "wrapper: 정상 종료" -ForegroundColor Green
            break
        }
        42 {
            Write-Host "wrapper: 업데이트 요청 - git pull 실행" -ForegroundColor Cyan
            Push-Location $runtimeDir
            git pull origin main
            # 의존성 설치 (requirements.txt 변경 대응)
            $pipExe = Join-Path $runtimeDir "venv\Scripts\pip.exe"
            $requirementsFile = Join-Path $runtimeDir "requirements.txt"
            if (Test-Path $requirementsFile) {
                Write-Host "wrapper: 의존성 설치 중..." -ForegroundColor Cyan
                & $pipExe install -r $requirementsFile --quiet
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "wrapper: 의존성 설치 완료" -ForegroundColor Green
                } else {
                    Write-Host "wrapper: 의존성 설치 실패 (계속 진행)" -ForegroundColor Yellow
                }
            }
            # MCP 의존성 설치 (mcp_requirements.txt 변경 대응)
            $mcpPipExe = Join-Path $runtimeDir "mcp_venv\Scripts\pip.exe"
            $mcpRequirementsFile = Join-Path $runtimeDir "mcp_requirements.txt"
            if ((Test-Path $mcpPipExe) -and (Test-Path $mcpRequirementsFile)) {
                Write-Host "wrapper: MCP 의존성 설치 중..." -ForegroundColor Cyan
                & $mcpPipExe install -r $mcpRequirementsFile --quiet
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "wrapper: MCP 의존성 설치 완료" -ForegroundColor Green
                } else {
                    Write-Host "wrapper: MCP 의존성 설치 실패 (계속 진행)" -ForegroundColor Yellow
                }
            }
            Pop-Location
            Sync-DevSeosoyoung  # 개발 소스 동기화
            Write-Host "wrapper: 업데이트 완료, 재시작..." -ForegroundColor Cyan
        }
        43 {
            Write-Host "wrapper: 재시작 요청" -ForegroundColor Cyan
        }
        default {
            Write-Host "wrapper: 비정상 종료, 5초 후 재시작..." -ForegroundColor Red
            Start-Sleep -Seconds 5
        }
    }

    if ($exitCode -eq 0) { break }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "wrapper: 종료 - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Stop-Transcript
