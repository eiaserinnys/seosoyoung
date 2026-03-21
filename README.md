# SeoSoyoung (서소영)

Slack 멘션으로 Claude Code를 호출하여
로컬 PC에서 여러가지 작업을 지원하거나
스스로 수정하는 작업을 자동화하는 봇입니다.

<!-- sentinel deploy test 2 -->

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
| 프로세스 관리 | Haniel (서비스 오케스트레이터) |
| MCP | FastMCP, supergateway |

## 아키텍처

```
  [Haniel]               ← 서비스 오케스트레이터 (WinSW Windows 서비스)
     │
     ├── mcp-seosoyoung      커스텀 MCP 서버 (3104)
     ├── mcp-eb-lore         eb_lore MCP 서버 (3108)
     ├── mcp-outline         Outline 위키 MCP (3103)
     ├── mcp-slack           Slack MCP (3101)
     ├── mcp-trello          Trello MCP (3102)
     └── soulstream-server   Claude Code 실행 서비스 (4105)
```

Haniel이 모든 서비스의 생명주기(시작, 헬스체크, 재시작, 배포)를 관리합니다.
bot과 rescue-bot은 별도 환경에서 독립 운영됩니다.

### Exit Code 체계

| Code | 의미 | 동작 |
|------|------|------|
| `0` | 정상 종료 | 프로세스 관리자 루프 탈출 |
| `42` | 코드 변경 감지 | 프로세스 관리자가 git pull + pip install 후 재시작 |
| `43` | 프로세스 재시작 | 해당 프로세스만 즉시 재시작 |
| `44` | 프로세스 관리자 전체 재시작 | 전체 재시작 |
| 기타 | 비정상 종료 | 지수적 백오프 후 재시작 |

## 설치

Haniel을 통해 설치합니다.

```powershell
# 1. Haniel 설치
irm https://raw.githubusercontent.com/eiaserinnys/Haniel/main/install-haniel.ps1 | iex

# 2. 설정 파일 URL 입력
# https://raw.githubusercontent.com/eiaserinnys/seosoyoung_workspace/main/seosoyoung.haniel.yaml

# 3. 설치 완료 후 서비스 시작
haniel start
```

Haniel이 수행하는 작업:
- 리포 클론 (workspace, seosoyoung, soulstream, eb_lore 등)
- Python 가상환경 생성 및 의존성 설치
- 서비스별 .env 파일 생성
- MCP 서버 설정 (.mcp.json)
- WinSW Windows 서비스 등록

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

## 프로젝트 구조

```
src/
├── seosoyoung/
│   ├── core/                # 플러그인 코어 (레지스트리, 훅, 매니저)
│   ├── plugin_sdk/          # 플러그인 SDK (Slack/Soulstream 백엔드 프로토콜)
│   ├── slackbot/            # Slack 봇 메인 모듈
│   │   ├── main.py          # 앱 진입점
│   │   ├── config.py        # 환경 변수 기반 설정
│   │   ├── handlers/        # 멘션, 메시지, 명령어 핸들러
│   │   ├── soulstream/      # Claude Code 실행 (세션, 인터벤션)
│   │   ├── presentation/    # 진행 상태 UI
│   │   ├── slack/           # Slack API 유틸리티
│   │   └── web/             # 웹 콘텐츠 추출
│   ├── claude/              # Claude Code SDK 래퍼
│   ├── mcp/                 # 커스텀 MCP 서버 (mcp-seosoyoung)
│   ├── rescue/              # 긴급 복구 봇
│   └── utils/               # 공통 유틸리티
```

### 플러그인 시스템

플러그인 코드는 별도 패키지 `seosoyoung-plugins`로 분리되어 있습니다.
`config/plugins.yaml` 레지스트리가 어떤 플러그인을 로드할지 정의하며,
각 플러그인의 런타임 설정(API 키 등)은 `config/` 하위의 개별 YAML 파일에 저장됩니다.

`config/` 하위의 모든 YAML 파일은 gitignored이며, 환경마다 별도로 설정해야 합니다.
초기 설정 시 `config/plugins.yaml.example`을 복사하여 사용하세요:

```bash
cp config/plugins.yaml.example config/plugins.yaml
# 필요에 따라 플러그인 활성화/비활성화 편집
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

주요 포트: 3101(slack), 3102(trello), 3103(outline), 3104(seosoyoung-mcp), 3106(bot shutdown), 3107(rescue), 3108(eb-lore), 4105(soulstream)

### 로그 확인

Haniel 대시보드에서 각 서비스의 로그를 확인할 수 있습니다.

```powershell
haniel status    # 서비스 상태 확인
haniel logs      # 로그 확인
```

## 테스트

```bash
pytest
```

## 라이선스

MIT License
