# SeoSoyoung (서소영)

Slack 멘션으로 Claude Code를 호출하여
로컬 PC에서 여러가지 작업을 지원하거나
스스로 수정하는 작업을 자동화하는 봇입니다.

## 개요

```
사용자: @[봇 이름] 질문/명령
   ↓
Slack Bot (slack_bolt, Socket Mode)
   ↓
Claude Code CLI/SDK 실행
   ↓
결과를 Slack 스레드에 회신
```

Slack에서 봇을 멘션하면 백그라운드에서 Claude Code를 실행하고, 결과를 같은 스레드에 반환합니다.

### 주요 기능

- **Claude Code 연동**: Slack 메시지를 Claude Code에 전달하고 결과 반환
- **세션 관리**: Slack 스레드별 대화 컨텍스트 유지
- **Trello 연동**: Trello 카드 감시 및 자동 작업 실행
- **번역 기능**: 특정 채널의 메시지 자동 번역
- **파일 첨부 / 이미지 생성**: 작업 결과를 파일로 첨부하거나 Gemini로 이미지 생성
- **MCP 서버**: Slack, Trello, Outline, eb-lore 등 외부 도구 연동

### 기술 스택

| 구성요소 | 기술 |
|---------|------|
| 언어 | Python 3.13 |
| Slack | slack_bolt (Socket Mode) |
| Claude | anthropic SDK, Claude Code CLI/SDK |
| 작업 관리 | Trello API |
| 검색 | Whoosh, kiwipiepy |
| 프로세스 관리 | supervisor (자체 구현), watchdog, NSSM |
| MCP | FastMCP, supergateway |

## 아키텍처

```
  [NSSM Windows Service]
         │
         ▼
  [watchdog.ps1]       ← 지수적 백오프, 자동 롤백, Claude Code 비상 복구
         │
         ▼
  [supervisor]         ← Python, 프로세스 라이프사이클 + 대시보드 (8042)
         │
         ├── bot                 Slack 봇 본체 (slack_bolt)
         ├── seosoyoung-soul     Claude Code 실행 서비스 (FastAPI, 3105)
         ├── mcp-seosoyoung      커스텀 MCP 서버 (3104)
         ├── mcp-eb-lore         eb_lore MCP 서버 (3108, 선택적)
         ├── mcp-outline         Outline 위키 MCP (3103, 선택적)
         ├── mcp-slack           Slack MCP (3101, 선택적)
         ├── mcp-trello          Trello MCP (3102, 선택적)
         └── rescue-bot          긴급 복구 봇 (선택적)
```

### 프로세스 관리 계층

| 계층 | 역할 |
|------|------|
| **NSSM** | Windows 서비스로 등록, 부팅 시 자동 시작. watchdog이 죽으면 재시작. |
| **watchdog.ps1** | supervisor를 감시. exit code에 따라 재시작, 업데이트, 롤백 판단. |
| **supervisor** | bot + MCP 서버들의 프로세스 관리. 헬스체크, git polling, 대시보드 제공. |

### Exit Code 체계

| Code | 의미 | 동작 |
|------|------|------|
| `0` | 정상 종료 | watchdog 루프 탈출 |
| `42` | 코드 변경 감지 | watchdog이 `git pull` + `pip install` 후 재시작 |
| `43` | 프로세스 재시작 | 해당 프로세스만 즉시 재시작 |
| `44` | supervisor 재시작 | supervisor 전체 재시작 (watchdog으로 위임) |
| 기타 | 비정상 종료 | 지수적 백오프 후 재시작 |

### 자동 업데이트

supervisor 내부의 `git_poller`가 60초마다 remote를 체크합니다.
변경이 감지되면 `deployer`가 활성 Claude Code 세션이 없을 때까지 대기한 뒤,
exit code 42로 supervisor를 종료합니다.
watchdog이 `git pull` → `pip install` → 재시작을 수행합니다.

### 자동 롤백

supervisor가 60초 미만 가동 후 종료되면 "빠른 크래시"로 판단합니다.
연속 3회 빠른 크래시가 발생하면 watchdog이 마지막으로 안정 동작한 커밋(known good commit)으로
`git reset --hard`를 실행하고, Claude Code 비상 복구 모드를 시작합니다.
비상 복구 모드에서는 Claude Code가 크래시 원인을 분석하고 자동 수정을 시도합니다.

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

### 기타

- **Python 3.13+**: [python.org](https://www.python.org/downloads/)
- **Node.js**: [nodejs.org](https://nodejs.org/) (MCP 서버 브릿지용)
- **NSSM** (선택): Windows 서비스 등록용. `winget install nssm`

## 빠른 시작 (setup.ps1)

`setup.ps1`은 리포 클론 없이 단독 실행 가능한 스크립트입니다. GitHub에서 스크립트만 다운로드하여 실행하면 전체 환경이 구성됩니다.

```powershell
# 1. setup.ps1 다운로드 (또는 리포에서 직접 복사)
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/eiaserinnys/seosoyoung/main/scripts/setup.ps1" -OutFile setup.ps1

# 2. 셋업 실행 (루트 디렉토리 지정)
.\setup.ps1 -RootDir "D:\seosoyoung"

# 3. .env 편집 (토큰, API 키 설정)
notepad D:\seosoyoung\runtime\.env

# 4. 서비스 시작
nssm start SeoSoyoungWatchdog
# 또는 직접 실행
powershell D:\seosoyoung\runtime\scripts\watchdog.ps1
```

`setup.ps1`이 수행하는 작업:
- 환경 검증 (Python, Node.js, Git)
- 루트 디렉토리 + 하위 구조 생성
- 리포 클론 → `runtime/`
- devClone 생성 → `workspace/.projects/seosoyoung/`
- Python 가상환경 생성 (venv, mcp_venv) 및 의존성 설치
- 설정 파일 복사 (.env.example → .env, watchdog_config)
- npm 글로벌 패키지 설치 (supergateway)
- NSSM 서비스 등록 (선택)

파라미터:
- `-RootDir` : 루트 디렉토리 (기본: 현재 위치/seosoyoung)
- `-BotName` : 봇 이름 (기본: seosoyoung)
- `-RepoUrl` : GitHub URL (기본: eiaserinnys/seosoyoung)
- `-SkipNssm` : NSSM 등록 건너뛰기

## 수동 설치

### 1. 폴더 구조

```
seosoyoung/                     ← 루트
├── runtime/                    ← 이 리포를 클론
│   ├── .env                    ← 환경 변수
│   ├── venv/                   ← 메인 가상환경
│   ├── mcp_venv/               ← MCP 서버 가상환경
│   ├── src/supervisor/         ← supervisor 모듈
│   ├── scripts/                ← watchdog, setup 등
│   ├── data/                   ← 상태 파일, 설정
│   ├── logs/                   ← 로그
│   ├── sessions/               ← Claude Code 세션
│   └── memory/                 ← 관찰 기억 데이터
│
└── workspace/                  ← Claude Code 작업 디렉토리
    └── .projects/
        └── seosoyoung/         ← devClone (개발용 클론)
```

### 2. 리포 클론 및 devClone

```powershell
mkdir seosoyoung
cd seosoyoung

# runtime (봇 실행 환경)
git clone https://github.com/eiaserinnys/seosoyoung.git runtime

# runtime 하위 디렉토리 생성
mkdir runtime/data
mkdir runtime/logs
mkdir runtime/sessions
mkdir runtime/memory

# workspace + devClone
mkdir workspace/.projects
git clone https://github.com/eiaserinnys/seosoyoung.git workspace/.projects/seosoyoung
```

### 3. 가상환경 및 의존성

```powershell
cd runtime

# 메인 가상환경
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# MCP 가상환경
python -m venv mcp_venv
.\mcp_venv\Scripts\pip install -r mcp_requirements.txt

# supergateway (MCP 서버 브릿지)
npm install -g supergateway
```

### 4. 환경 변수

```powershell
copy .env.example .env
notepad .env
```

`.env` 파일에 아래 값을 설정하세요. `SOYOUNG_ROOT`를 루트 디렉토리로 지정해야 supervisor가 경로를 찾을 수 있습니다. 상세 항목은 [환경 변수 레퍼런스](#환경-변수-레퍼런스)를 참고하세요.

### 5. NSSM 서비스 등록 (선택)

```powershell
# 관리자 PowerShell에서 실행
.\scripts\install-service.ps1
```

또는 watchdog을 직접 실행하여 포그라운드로 운영할 수도 있습니다:

```powershell
powershell .\scripts\watchdog.ps1
```

## 서비스 관리

### NSSM 명령

```powershell
nssm start SeoSoyoungWatchdog       # 시작
nssm stop SeoSoyoungWatchdog        # 중지
nssm restart SeoSoyoungWatchdog     # 재시작
nssm status SeoSoyoungWatchdog      # 상태 확인
nssm remove SeoSoyoungWatchdog confirm  # 서비스 제거
```

### 대시보드

supervisor가 실행 중이면 `http://localhost:8042`에서 대시보드에 접근할 수 있습니다.

**REST API:**

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/api/status` | GET | 전체 프로세스 상태 조회 |
| `/api/process/{name}/start` | POST | 프로세스 시작 |
| `/api/process/{name}/stop` | POST | 프로세스 중지 |
| `/api/process/{name}/restart` | POST | 프로세스 재시작 |

### 기타 스크립트

| 스크립트 | 설명 |
|---------|------|
| `scripts/setup.ps1` | 초기 환경 구성 |
| `scripts/watchdog.ps1` | supervisor 감시 (NSSM이 실행) |
| `scripts/install-service.ps1` | NSSM 서비스 등록 (관리자) |
| `scripts/start.ps1` | git pull + wrapper 실행 (레거시) |
| `scripts/wrapper.ps1` | 봇 프로세스 래퍼 (레거시) |
| `scripts/stop.ps1` | 봇 프로세스 강제 종료 |

## 환경 변수 레퍼런스

### 필수

| 변수 | 설명 |
|------|------|
| `SLACK_BOT_TOKEN` | Slack Bot 토큰 (xoxb-...) |
| `SLACK_APP_TOKEN` | Slack App 토큰 (xapp-...) |
| `ANTHROPIC_API_KEY` | Anthropic API 키 |

### Slack / Claude

| 변수 | 설명 |
|------|------|
| `LOG_PATH` | 로그 저장 경로 |
| `SESSION_PATH` | 세션 저장 경로 |
| `ALLOWED_USERS` | 봇 사용 허용 사용자 ID (쉼표 구분) |
| `ADMIN_USERS` | 관리자 사용자 ID (쉼표 구분) |
| `DEBUG` | 디버그 모드 (true/false) |
| `NOTIFY_CHANNEL` | 알림 채널 ID |

### 번역

| 변수 | 설명 |
|------|------|
| `TRANSLATE_API_KEY` | 번역용 API 키 (별도 과금용) |
| `TRANSLATE_CHANNELS` | 번역 대상 채널 ID (쉼표 구분) |
| `TRANSLATE_MODEL` | 번역에 사용할 Claude 모델 |
| `TRANSLATE_CONTEXT_COUNT` | 번역 컨텍스트 메시지 수 |

### Recall (도구 사전 분석)

| 변수 | 설명 |
|------|------|
| `RECALL_API_KEY` | Recall용 API 키 |
| `RECALL_MODEL` | Recall 모델 (예: claude-haiku-4-5) |
| `RECALL_ENABLED` | 활성화 여부 (true/false) |
| `RECALL_THRESHOLD` | 도구 호출 임계치 |
| `RECALL_TIMEOUT` | 타임아웃 (초) |

### 이미지 생성

| 변수 | 설명 |
|------|------|
| `GEMINI_API_KEY` | Gemini API 키 |
| `GEMINI_MODEL` | Gemini 모델명 |

### 관찰 기억 (Observational Memory)

| 변수 | 설명 |
|------|------|
| `MEMORY_PATH` | 기억 데이터 저장 경로 |
| `OPENAI_API_KEY` | OpenAI API 키 (임베딩용) |
| `OM_MODEL` | OM 모델 |
| `OM_ENABLED` | 활성화 여부 (true/false) |

### MCP 서버 연동

| 변수 | 설명 |
|------|------|
| `OUTLINE_API_KEY` | Outline API 키 |
| `OUTLINE_API_URL` | Outline API URL |
| `SLACK_MCP_XOXC_TOKEN` | Slack MCP xoxc 토큰 |
| `SLACK_MCP_XOXD_TOKEN` | Slack MCP xoxd 토큰 |
| `TRELLO_API_KEY` | Trello API 키 |
| `TRELLO_TOKEN` | Trello 토큰 |

### Supervisor

| 변수 | 설명 |
|------|------|
| `SOYOUNG_ROOT` | 루트 디렉토리 (기본: D:/soyoung_root) |
| `SUPERVISOR_DASHBOARD_PORT` | 대시보드 포트 (기본: 8042) |
| `CLAUDE_CLI_DIR` | Claude CLI 디렉토리 (SYSTEM 계정용) |
| `SUPERGATEWAY_PATH` | supergateway index.js 경로 |
| `MCP_SERVERS_DIR` | MCP 서버 작업 디렉토리 |
| `RESCUE_SLACK_BOT_TOKEN` | 긴급 복구 봇 토큰 |
| `RESCUE_SLACK_APP_TOKEN` | 긴급 복구 봇 앱 토큰 |

## 프로젝트 구조

```
src/
├── seosoyoung/
│   ├── main.py              # 앱 진입점
│   ├── config.py            # 환경 변수 기반 설정
│   ├── auth.py              # 사용자 권한 관리
│   ├── bot/                 # 봇 유틸리티
│   ├── claude/
│   │   ├── agent_runner.py  # Claude Code SDK 래퍼
│   │   ├── executor.py      # 실행 로직 (인터벤션 지원)
│   │   ├── session.py       # 스레드-세션 매핑
│   │   └── security.py      # 보안 레이어
│   ├── handlers/
│   │   ├── mention.py       # @멘션 핸들러
│   │   ├── message.py       # 스레드 메시지 핸들러
│   │   └── translate.py     # 번역 핸들러
│   ├── mcp/                 # 커스텀 MCP 서버 (mcp-seosoyoung)
│   ├── memory/              # 관찰 기억 시스템
│   ├── recall/              # 도구/에이전트 라우팅
│   ├── rescue/              # 긴급 복구 봇
│   ├── slack/               # Slack API 유틸리티
│   ├── slackbot/            # Slack 봇 메인 모듈
│   ├── soul/                # Claude Code 실행 서비스
│   ├── translator/          # 번역 로직 및 용어집
│   ├── trello/              # Trello 카드 감시 및 자동 실행
│   └── search/              # 대사 검색 인덱스/엔진
│
├── supervisor/              # 프로세스 관리자
│   ├── __main__.py          # 진입점, 메인 루프
│   ├── config.py            # 프로세스 정의, 경로 해석
│   ├── models.py            # ProcessConfig, ExitAction 등
│   ├── process_manager.py   # 프로세스 시작/중지/재시작
│   ├── dashboard.py         # FastAPI 대시보드
│   ├── deployer.py          # 배포 상태 머신
│   ├── git_poller.py        # Git 변경 감지
│   ├── job_object.py        # Windows Job Object (자식 프로세스 정리)
│   ├── session_monitor.py   # Claude Code 세션 감시
│   └── notifier.py          # Slack 알림
│
scripts/
├── setup.ps1                # 초기 환경 구성
├── watchdog.ps1             # supervisor 감시
├── install-service.ps1      # NSSM 서비스 등록
├── start.ps1                # 봇 시작 (레거시)
├── wrapper.ps1              # 봇 래퍼 (레거시)
└── stop.ps1                 # 봇 강제 종료
```

## 트러블슈팅

### 포트 충돌

프로세스가 비정상 종료하면 포트를 점유한 고아 프로세스가 남을 수 있습니다.

```powershell
# 포트를 점유한 프로세스 확인
netstat -ano | findstr :3104

# PID로 강제 종료
taskkill /F /PID <PID>
```

주요 포트: 3101(slack), 3102(trello), 3103(outline), 3104(seosoyoung-mcp), 3105(soul), 3106(bot shutdown), 3107(rescue), 3108(eb-lore), 8042(dashboard)

### 로그 확인

| 로그 | 위치 |
|------|------|
| watchdog | `{runtime}/logs/watchdog.log` |
| supervisor | 콘솔 출력 (NSSM: `{runtime}/logs/service_stdout.log`) |
| 각 프로세스 | `{runtime}/logs/{프로세스명}-out.log`, `{프로세스명}-error.log` |
| pip 설치 | `{runtime}/logs/pip_*.log` |
| 비상 복구 | `{runtime}/logs/emergency_*.log` |

### NSSM 서비스 재설치

```powershell
# 관리자 PowerShell
nssm stop SeoSoyoungWatchdog
nssm remove SeoSoyoungWatchdog confirm
.\scripts\install-service.ps1
```

### Session 0 환경변수 이슈

NSSM이 LocalSystem(Session 0)으로 실행할 때 사용자 환경변수를 상속하지 않습니다.
supervisor가 `.env` 파일을 자동으로 로드하므로 대부분의 경우 문제없지만,
`claude` CLI가 PATH에 없을 수 있습니다.

해결 방법:
- `.env`에 `CLAUDE_CLI_DIR=C:\Users\{사용자}\.local\bin`을 추가
- 또는 NSSM 환경변수 편집: `nssm set SeoSoyoungWatchdog AppEnvironmentExtra PATH=...`

### watchdog 상태 초기화

watchdog이 최대 재시도를 초과하여 멈춘 경우:

```powershell
# 상태 파일 삭제 (연속 실패 카운터 초기화)
Remove-Item {runtime}\data\watchdog_state.json

# 서비스 재시작
nssm restart SeoSoyoungWatchdog
```

## 테스트

```bash
pytest
```

## 라이선스

MIT License
