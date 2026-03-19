param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Command,
    [string]$EnvPath = ""
)

# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

# .env 파일 경로 결정
# -EnvPath가 지정되면 해당 파일 사용, 없으면 CWD의 .env 사용
if ($EnvPath -ne "") {
    $envFile = $EnvPath
} else {
    $envFile = Join-Path (Get-Location) ".env"
}

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        # 빈 줄 또는 주석 무시
        if ($line -eq "" -or $line.StartsWith("#")) {
            return
        }
        # KEY=VALUE 형태 파싱
        $eqIndex = $line.IndexOf("=")
        if ($eqIndex -gt 0) {
            $key = $line.Substring(0, $eqIndex).Trim()
            $value = $line.Substring($eqIndex + 1).Trim()
            # 따옴표 제거 (큰따옴표 또는 작은따옴표)
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

# 명령 실행 후 exit code 반환
cmd.exe /c $Command
exit $LASTEXITCODE
