# SeoSoyoung (서소영)

Slack 멘션으로 Claude Code를 호출하여
로컬 PC에서 여러가지 작업을 지원하거나
스스로 수정하는 작업을 자동화하는 봇입니다.

## 개요

```
사용자: @[봇 이름] 질문/명령
   ↓
Slack Bot (slack_bolt)
   ↓
Claude Code CLI/SDK 실행
   ↓
결과를 Slack 스레드에 회신
```

Slack에서 봇을 멘션하면 백그라운드에서 Claude Code를 실행하고, 결과를 같은 스레드에 반환합니다.

## 주요 기능

- **Claude Code 연동**: Slack 메시지를 Claude Code에 전달하고 결과 반환
- **세션 관리**: Slack 스레드별 대화 컨텍스트 유지
- **Trello 연동**: Trello 카드 감시 및 자동 작업 실행
- **번역 기능**: 특정 채널의 메시지 자동 번역
- **파일 첨부**: 작업 결과를 파일로 첨부하여 전송

## 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 언어 | Python 3.13 |
| Slack | slack_bolt (Socket Mode) |
| Claude | anthropic SDK, Claude Code CLI/SDK |
| 작업 관리 | Trello API |
| 검색 | Whoosh, kiwipiepy |

## 프로젝트 구조

```
src/seosoyoung/
├── main.py           # 앱 진입점
├── config.py         # 환경 변수 기반 설정
├── auth.py           # 사용자 권한 관리
├── claude/
│   ├── runner.py     # Claude Code CLI 래퍼
│   ├── agent_runner.py # Claude Code SDK 래퍼
│   ├── session.py    # 스레드-세션 매핑
│   └── security.py   # 보안 레이어
├── handlers/
│   ├── mention.py    # @멘션 핸들러
│   ├── message.py    # 스레드 메시지 핸들러
│   └── translate.py  # 번역 핸들러
├── slack/
│   ├── helpers.py    # Slack API 유틸리티
│   └── file_handler.py # 파일 업로드 처리
├── trello/
│   ├── client.py     # Trello API 클라이언트
│   └── watcher.py    # 카드 감시 워커
├── translator/
│   ├── translator.py # 번역 로직
│   └── glossary.py   # 용어집 관리
└── search/
    ├── indexer.py    # 검색 인덱스 생성
    └── searcher.py   # 검색 실행
```

## 사전 준비

### Slack 앱 생성

Slack 앱은 직접 생성해야 합니다. [Slack API](https://api.slack.com/apps)에서 새 앱을 만들고 아래 설정을 적용하세요.

**필요한 권한 (Bot Token Scopes):**
- `app_mentions:read` - 멘션 읽기
- `chat:write` - 메시지 전송
- `files:write` - 파일 업로드
- `channels:history` - 채널 기록 읽기
- `groups:history` - 비공개 채널 기록 읽기

**Event Subscriptions:**
- `app_mention` - 봇 멘션 이벤트
- `message.channels` - 채널 메시지 (번역 기능용)

**Socket Mode:**
- Socket Mode를 활성화하고 App-Level Token을 발급받으세요.

### Claude Code CLI

[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)를 설치하고 인증을 완료하세요.

## 실행 환경 구성

이 프로젝트는 다음과 같은 폴더 구조를 권장합니다:

```
your_root/
├── [봇이름]_runtime/      # 봇 실행 환경
│   ├── .env               # 환경 변수 (토큰, API 키 등)
│   ├── logs/              # 로그 파일
│   ├── sessions/          # Claude Code 세션 데이터
│   └── scripts/
│       └── start.ps1      # 실행 스크립트
│
└── slackbot_workspace/    # 작업 디렉토리 (Claude Code의 cwd)
    ├── seosoyoung/        # 이 리포지터리 클론
    └── [작업용 리포지터리들]
```

### 1. 폴더 생성

```powershell
# 루트 폴더 생성
mkdir your_root
cd your_root

# 런타임 폴더 생성
mkdir mybot_runtime
mkdir mybot_runtime/logs
mkdir mybot_runtime/sessions
mkdir mybot_runtime/scripts

# 작업 디렉토리 생성
mkdir slackbot_workspace
```

### 2. 리포지터리 클론

```powershell
cd slackbot_workspace
git clone https://github.com/eiaserinnys/seosoyoung.git
```

### 3. 의존성 설치

```powershell
cd seosoyoung
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`mybot_runtime/.env` 파일을 생성하고 아래 내용을 채우세요:

```env
# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Claude
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Paths
LOG_PATH=D:\your_root\mybot_runtime\logs
SESSION_PATH=D:\your_root\mybot_runtime\sessions

# Permissions
ALLOWED_USERS=slack_user_id1,slack_user_id2
ADMIN_USERS=slack_user_id1

# Options
DEBUG=false
CLAUDE_USE_SDK=true
NOTIFY_CHANNEL=C0123456789

# Trello (선택)
TRELLO_API_KEY=
TRELLO_TOKEN=
TRELLO_BOARD_ID=
TRELLO_NOTIFY_CHANNEL=
TRELLO_TO_GO_LIST_ID=
TRELLO_BACKLOG_LIST_ID=
TRELLO_IN_PROGRESS_LIST_ID=
TRELLO_REVIEW_LIST_ID=
TRELLO_DONE_LIST_ID=

# 번역 기능 (선택)
TRANSLATE_API_KEY=
TRANSLATE_CHANNELS=
TRANSLATE_MODEL=claude-sonnet-4-20250514
TRANSLATE_CONTEXT_COUNT=10
TRANSLATE_DEBUG_CHANNEL=
```

### 5. 실행 스크립트 생성

`mybot_runtime/scripts/start.ps1`:

```powershell
# UTF-8 인코딩 설정
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$RUNTIME = "$ROOT\mybot_runtime"
$WORKSPACE = "$ROOT\slackbot_workspace"

# 환경 변수 로드
Get-Content "$RUNTIME\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}

# 봇 실행
Set-Location $WORKSPACE
python -m seosoyoung.main
```

### 6. 실행

```powershell
cd mybot_runtime/scripts
.\start.ps1
```

## 테스트

```bash
pytest
```

## 환경 변수 레퍼런스

| 변수 | 필수 | 설명 |
|------|:----:|------|
| `SLACK_BOT_TOKEN` | O | Slack Bot 토큰 (xoxb-...) |
| `SLACK_APP_TOKEN` | O | Slack App 토큰 (xapp-...) |
| `ANTHROPIC_API_KEY` | O | Anthropic API 키 |
| `LOG_PATH` | | 로그 저장 경로 |
| `SESSION_PATH` | | 세션 저장 경로 |
| `ALLOWED_USERS` | | 봇 사용 허용 사용자 ID (쉼표 구분) |
| `ADMIN_USERS` | | 관리자 사용자 ID (쉼표 구분) |
| `DEBUG` | | 디버그 모드 (true/false) |
| `CLAUDE_USE_SDK` | | SDK 모드 사용 (true/false) |
| `NOTIFY_CHANNEL` | | 알림 채널 ID |
| `TRELLO_API_KEY` | | Trello API 키 |
| `TRELLO_TOKEN` | | Trello 토큰 |
| `TRELLO_BOARD_ID` | | Trello 보드 ID |
| `TRANSLATE_API_KEY` | | 번역용 API 키 (별도 과금용) |
| `TRANSLATE_CHANNELS` | | 번역 대상 채널 ID (쉼표 구분) |

## 라이선스

MIT License
