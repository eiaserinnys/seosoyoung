# Git hooks 설치 스크립트 (PowerShell)
# 사용법: .init\install.ps1

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$HooksSrc = Join-Path $ScriptDir "hooks"
$HooksDst = Join-Path $RepoRoot ".git\hooks"

Write-Host "Git hooks 설치 중..."

Get-ChildItem -Path $HooksSrc -File | ForEach-Object {
    $hookName = $_.Name
    $src = $_.FullName
    $dst = Join-Path $HooksDst $hookName

    Copy-Item -Path $src -Destination $dst -Force
    Write-Host "  설치됨: $hookName"
}

Write-Host "완료."
