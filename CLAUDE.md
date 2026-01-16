# SeoSoyoung

Claude Code CLI를 Slack과 통합하는 자동화 봇

## 프로젝트 개요

Slack에서 @seosoyoung 멘션으로 Claude Code 작업을 요청하면, 백그라운드에서 Claude Code CLI를 실행하여 코드 분석, 검색, 편집 작업을 수행하고 결과를 Slack으로 반환합니다.

## 기술 스택

- Python 3.13
- slack_bolt: Slack 봇 프레임워크
- anthropic: Claude API 클라이언트
- pytest: 테스트 프레임워크

## 프로젝트 구조

```
src/seosoyoung/
├── main.py           # Slack 봇 메인 로직
├── config.py         # 환경 변수 기반 설정 관리
├── bot/              # 봇 관련 유틸리티
├── claude/
│   ├── runner.py     # Claude Code CLI 래퍼
│   ├── security.py   # 보안 레이어
│   └── session.py    # Slack 스레드-Claude 세션 매핑
└── workflows/        # 워크플로우 모듈
```

## 개발 가이드

### 환경 설정

```bash
cp .env.example .env
# .env 파일에 Slack 토큰, Anthropic API 키 등 설정
```

### 테스트

```bash
pytest
```

## 코딩 컨벤션

- 비동기 함수는 `async/await` 사용
- 보안 관련 코드는 `claude/security.py`에서 관리
- 세션 데이터는 JSON 파일로 영구 저장
- 긴 Slack 메시지는 자동 분할 전송
