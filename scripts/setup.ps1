<#
.SYNOPSIS
    seosoyoung 봇 초기 환경 구성 스크립트.

.DESCRIPTION
    이 스크립트 하나로 봇 실행 환경을 처음부터 구성합니다.
    리포 클론을 전제하지 않으며, 스크립트 단독으로 실행 가능합니다.

    실행 흐름:
      1. 환경 검증 (Python 3.13+, Node.js, Git)
      2. 루트 디렉토리 + 하위 구조 생성
      3. 리포 클론 → runtime/
      4. devClone 생성 → workspace/.projects/{봇이름}/
      5. Python 가상환경 + 의존성 설치
      6. 설정 파일 복사 (.env, watchdog_config.json)
      7. npm 글로벌 패키지 설치 (supergateway)
      8. NSSM 서비스 등록 (선택)

    결과 폴더 구조:
      {RootDir}/
      ├── runtime/          ← 리포 클론 + venv, logs, data 등
      └── workspace/        ← Claude Code 작업 디렉토리
          └── .projects/
              └── {봇이름}/ ← devClone

.PARAMETER RootDir
    루트 디렉토리. 기본값: 현재 위치 하위의 'seosoyoung'.

.PARAMETER BotName
    봇 이름. 기본값: seosoyoung.

.PARAMETER RepoUrl
    GitHub 리포 URL.

.PARAMETER SkipNssm
    NSSM 서비스 등록을 건너뜁니다.

.EXAMPLE
    .\setup.ps1 -RootDir "D:\seosoyoung"
    .\setup.ps1 -RootDir "D:\seosoyoung" -BotName "mybot" -RepoUrl "https://github.com/user/repo.git"
    .\setup.ps1 -SkipNssm
#>

param(
    [string]$RootDir,
    [string]$BotName = "seosoyoung",
    [string]$RepoUrl = "https://github.com/eiaserinnys/seosoyoung.git",
    [switch]$SkipNssm
)

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ErrorActionPreference = "Stop"

# ============================================================
# 경로 해석
# ============================================================

if (-not $RootDir) {
    $RootDir = Join-Path (Get-Location) "seosoyoung"
}

$runtimeDir = Join-Path $RootDir "runtime"
$workspaceDir = Join-Path $RootDir "workspace"
$devCloneDir = Join-Path $workspaceDir ".projects\$BotName"
$scriptsDir = Join-Path $runtimeDir "scripts"

# ============================================================
# 유틸리티
# ============================================================

function Write-Step($step, $message) {
    Write-Host ""
    Write-Host "[$step] $message" -ForegroundColor Cyan
    Write-Host ("-" * 50) -ForegroundColor DarkGray
}

function Confirm-Step($message) {
    $answer = Read-Host "$message (y/n, 기본: y)"
    if ($answer -and $answer.ToLower() -notin @("y", "yes")) {
        Write-Host "  건너뜁니다." -ForegroundColor Yellow
        return $false
    }
    return $true
}

# ============================================================
# 1. 환경 검증
# ============================================================

Write-Step "1/8" "환경 검증"

# Python
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python을 찾을 수 없습니다. Python 3.13 이상을 설치해 주세요." -ForegroundColor Red
    exit 1
}
$versionMatch = [regex]::Match($pythonVersion, "(\d+)\.(\d+)")
if ($versionMatch.Success) {
    $major = [int]$versionMatch.Groups[1].Value
    $minor = [int]$versionMatch.Groups[2].Value
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 13)) {
        Write-Host "[ERROR] Python 3.13 이상이 필요합니다. (현재: $pythonVersion)" -ForegroundColor Red
        exit 1
    }
}
Write-Host "  Python: $pythonVersion" -ForegroundColor Green

# Node.js
$nodeVersion = node --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Node.js를 찾을 수 없습니다." -ForegroundColor Red
    exit 1
}
Write-Host "  Node.js: $nodeVersion" -ForegroundColor Green

# Git
$gitVersion = git --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Git을 찾을 수 없습니다." -ForegroundColor Red
    exit 1
}
Write-Host "  Git: $gitVersion" -ForegroundColor Green

Write-Host ""
Write-Host "  Root:      $RootDir" -ForegroundColor White
Write-Host "  Runtime:   $runtimeDir" -ForegroundColor White
Write-Host "  Workspace: $workspaceDir" -ForegroundColor White
Write-Host "  DevClone:  $devCloneDir" -ForegroundColor White
Write-Host "  RepoUrl:   $RepoUrl" -ForegroundColor White

if (-not (Confirm-Step "이 설정으로 진행하시겠습니까?")) {
    Write-Host "설정을 중단합니다." -ForegroundColor Yellow
    exit 0
}

# ============================================================
# 2. 루트 디렉토리 생성
# ============================================================

Write-Step "2/8" "디렉토리 구조 생성"

if (-not (Test-Path $RootDir)) {
    New-Item -ItemType Directory -Path $RootDir -Force | Out-Null
    Write-Host "  Created: $RootDir" -ForegroundColor Green
}

# workspace 하위 디렉토리
$dirs = @(
    (Join-Path $workspaceDir ".projects"),
    (Join-Path $workspaceDir ".local\artifacts"),
    (Join-Path $workspaceDir ".local\incoming"),
    (Join-Path $workspaceDir ".local\index"),
    (Join-Path $workspaceDir ".local\tmp")
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Green
    } else {
        Write-Host "  Exists:  $dir" -ForegroundColor DarkGray
    }
}

# ============================================================
# 3. 리포 클론 → runtime/
# ============================================================

Write-Step "3/8" "리포 클론 (runtime)"

if (Test-Path (Join-Path $runtimeDir ".git")) {
    Write-Host "  이미 클론되어 있습니다: $runtimeDir" -ForegroundColor DarkGray
    Write-Host "  git pull 실행 중..." -ForegroundColor Cyan
    git -C $runtimeDir pull origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] git pull 실패 (계속 진행)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  git clone 실행 중..." -ForegroundColor Cyan
    git clone $RepoUrl $runtimeDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] git clone 실패" -ForegroundColor Red
        exit 1
    }
    Write-Host "  runtime 클론 완료" -ForegroundColor Green
}

# runtime 하위 디렉토리 (클론 후 생성)
$runtimeDirs = @(
    (Join-Path $runtimeDir "data"),
    (Join-Path $runtimeDir "logs"),
    (Join-Path $runtimeDir "sessions"),
    (Join-Path $runtimeDir "memory")
)

foreach ($dir in $runtimeDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Green
    }
}

# ============================================================
# 4. devClone 생성
# ============================================================

Write-Step "4/8" "devClone (개발용 클론)"

if (Test-Path (Join-Path $devCloneDir ".git")) {
    Write-Host "  이미 존재합니다: $devCloneDir" -ForegroundColor DarkGray
    Write-Host "  git pull 실행 중..." -ForegroundColor Cyan
    git -C $devCloneDir pull origin main
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] git pull 실패 (계속 진행)" -ForegroundColor Yellow
    }
} else {
    if (Confirm-Step "devClone을 생성하시겠습니까?") {
        Write-Host "  git clone 실행 중..." -ForegroundColor Cyan
        git clone $RepoUrl $devCloneDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] git clone 실패" -ForegroundColor Red
            exit 1
        }
        Write-Host "  devClone 생성 완료" -ForegroundColor Green
    }
}

# ============================================================
# 5. Python 가상환경 + 의존성 설치
# ============================================================

Write-Step "5/8" "Python 가상환경 + 의존성 설치"

# venv (메인)
$venvDir = Join-Path $runtimeDir "venv"
if (-not (Test-Path $venvDir)) {
    if (Confirm-Step "메인 가상환경(venv)을 생성하시겠습니까?") {
        Write-Host "  venv 생성 중..." -ForegroundColor Cyan
        python -m venv $venvDir
        Write-Host "  venv 생성 완료" -ForegroundColor Green
    }
} else {
    Write-Host "  venv 이미 존재: $venvDir" -ForegroundColor DarkGray
}

$venvPip = Join-Path $venvDir "Scripts\pip.exe"
$requirementsFile = Join-Path $runtimeDir "requirements.txt"
if ((Test-Path $venvPip) -and (Test-Path $requirementsFile)) {
    Write-Host "  requirements.txt 설치 중..." -ForegroundColor Cyan
    & $venvPip install -r $requirementsFile --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  requirements.txt 설치 완료" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] 일부 패키지 설치 실패 (계속 진행)" -ForegroundColor Yellow
    }
}

# mcp_venv
$mcpVenvDir = Join-Path $runtimeDir "mcp_venv"
if (-not (Test-Path $mcpVenvDir)) {
    if (Confirm-Step "MCP 가상환경(mcp_venv)을 생성하시겠습니까?") {
        Write-Host "  mcp_venv 생성 중..." -ForegroundColor Cyan
        python -m venv $mcpVenvDir
        Write-Host "  mcp_venv 생성 완료" -ForegroundColor Green
    }
} else {
    Write-Host "  mcp_venv 이미 존재: $mcpVenvDir" -ForegroundColor DarkGray
}

$mcpPip = Join-Path $mcpVenvDir "Scripts\pip.exe"
$mcpRequirements = Join-Path $runtimeDir "mcp_requirements.txt"
if ((Test-Path $mcpPip) -and (Test-Path $mcpRequirements)) {
    Write-Host "  mcp_requirements.txt 설치 중..." -ForegroundColor Cyan
    & $mcpPip install -r $mcpRequirements --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  mcp_requirements.txt 설치 완료" -ForegroundColor Green
    } else {
        Write-Host "  [WARN] 일부 MCP 패키지 설치 실패 (계속 진행)" -ForegroundColor Yellow
    }
}

# .pth 파일 생성 (PYTHONPATH 대체)
# supervisor가 환경변수를 주입하지 않으므로, 각 venv에서 모듈 경로를 직접 인식하도록 함
Write-Host "  .pth 파일 생성 중..." -ForegroundColor Cyan

$venvSitePackages = Join-Path $venvDir "Lib\site-packages"
$mcpSitePackages = Join-Path $mcpVenvDir "Lib\site-packages"

if (Test-Path $venvSitePackages) {
    $pthContent = (Join-Path $runtimeDir "src").Replace("\", "/")
    Set-Content -Path (Join-Path $venvSitePackages "supervisor.pth") -Value $pthContent -Encoding UTF8
    Write-Host "  venv: supervisor.pth 생성 완료" -ForegroundColor Green
}

if (Test-Path $mcpSitePackages) {
    $mcpPthLines = @(
        (Join-Path $devCloneDir "src").Replace("\", "/"),
        (Join-Path $workspaceDir ".projects\eb_lore").Replace("\", "/")
    )
    Set-Content -Path (Join-Path $mcpSitePackages "mcp-paths.pth") -Value ($mcpPthLines -join "`n") -Encoding UTF8
    Write-Host "  mcp_venv: mcp-paths.pth 생성 완료" -ForegroundColor Green
}

# ============================================================
# 6. 설정 파일 복사
# ============================================================

Write-Step "6/8" "설정 파일"

# .env
$envFile = Join-Path $runtimeDir ".env"
$envExample = Join-Path $runtimeDir ".env.example"
if (-not (Test-Path $envFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $envFile
        Write-Host "  .env.example -> .env 복사 완료" -ForegroundColor Green
        Write-Host "  [TODO] .env 파일을 열어 토큰과 API 키를 설정해 주세요!" -ForegroundColor Yellow
    } else {
        Write-Host "  [WARN] .env.example이 없습니다. .env를 직접 생성해 주세요." -ForegroundColor Yellow
    }
} else {
    Write-Host "  .env 이미 존재 (건너뜀)" -ForegroundColor DarkGray
}

# watchdog_config.json
$watchdogConfig = Join-Path $runtimeDir "data\watchdog_config.json"
$watchdogTemplate = Join-Path $scriptsDir "watchdog_config.template.json"
if (-not (Test-Path $watchdogConfig)) {
    if (Test-Path $watchdogTemplate) {
        Copy-Item $watchdogTemplate $watchdogConfig
        Write-Host "  watchdog_config.template.json -> data/watchdog_config.json 복사 완료" -ForegroundColor Green
        Write-Host "  [TODO] Slack 웹훅 URL을 설정하면 알림을 받을 수 있습니다." -ForegroundColor Yellow
    } else {
        Write-Host "  [WARN] watchdog_config.template.json이 없습니다." -ForegroundColor Yellow
    }
} else {
    Write-Host "  watchdog_config.json 이미 존재 (건너뜀)" -ForegroundColor DarkGray
}

# ============================================================
# 7. npm 글로벌 패키지 설치
# ============================================================

Write-Step "7/8" "npm 글로벌 패키지 (supergateway)"

$sgInstalled = npm list -g supergateway 2>$null
if ($LASTEXITCODE -ne 0) {
    if (Confirm-Step "supergateway를 글로벌 설치하시겠습니까?") {
        npm install -g supergateway
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  supergateway 설치 완료" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] supergateway 설치 실패 (MCP 서버 브릿지 없이는 일부 기능 제한)" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  supergateway 이미 설치됨" -ForegroundColor DarkGray
}

# ============================================================
# 8. NSSM 서비스 등록
# ============================================================

Write-Step "8/8" "NSSM 서비스 등록"

if ($SkipNssm) {
    Write-Host "  -SkipNssm 플래그로 건너뜁니다." -ForegroundColor Yellow
} else {
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $nssm) {
        Write-Host "  NSSM이 설치되어 있지 않습니다." -ForegroundColor Yellow
        Write-Host "  설치: winget install nssm" -ForegroundColor Yellow
        Write-Host "  NSSM 없이도 scripts/watchdog.ps1을 직접 실행하여 봇을 운영할 수 있습니다." -ForegroundColor Yellow
    } else {
        $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if (-not $isAdmin) {
            Write-Host "  NSSM 서비스 등록은 관리자 권한이 필요합니다." -ForegroundColor Yellow
            Write-Host "  관리자 PowerShell에서 다음을 실행하세요:" -ForegroundColor Yellow
            Write-Host "    $scriptsDir\install-service.ps1" -ForegroundColor White
        } else {
            if (Confirm-Step "NSSM으로 Windows 서비스를 등록하시겠습니까?") {
                & (Join-Path $scriptsDir "install-service.ps1")
            }
        }
    }
}

# ============================================================
# 완료
# ============================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 초기 설정 완료!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[다음 단계]" -ForegroundColor Yellow
Write-Host ""

if (-not (Test-Path $envFile) -or (Get-Content $envFile -Raw) -match "xoxb-\.\.\.") {
    Write-Host "  1. .env 파일 편집 (필수)" -ForegroundColor White
    Write-Host "     $envFile" -ForegroundColor Gray
    Write-Host "     SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_API_KEY 등을 설정하세요." -ForegroundColor Gray
    Write-Host ""
}

Write-Host "  2. SOYOUNG_ROOT 환경변수 설정 (필수)" -ForegroundColor White
Write-Host "     supervisor가 경로를 찾을 수 있도록 루트 디렉토리를 지정하세요." -ForegroundColor Gray
Write-Host "     .env에 추가: SOYOUNG_ROOT=$RootDir" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. 서비스 시작" -ForegroundColor White
Write-Host "     nssm start SeoSoyoungWatchdog          # NSSM 서비스로 시작" -ForegroundColor Gray
Write-Host "     또는" -ForegroundColor DarkGray
Write-Host "     powershell $scriptsDir\watchdog.ps1     # 직접 실행 (포그라운드)" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. 대시보드 확인" -ForegroundColor White
Write-Host "     http://localhost:8042" -ForegroundColor Gray
Write-Host ""
