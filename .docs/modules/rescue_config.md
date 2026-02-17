# rescue/config.py

> 경로: `seosoyoung/rescue/config.py`

## 개요

rescue-bot 환경변수 설정

메인 봇과 완전 독립된 별도 Slack App 토큰을 사용합니다.

## 클래스

### `RescueConfig`
- 위치: 줄 14
- 설명: rescue-bot 설정

#### 메서드

- `validate(cls)` (줄 28): 필수 환경변수 검증
- `get_working_dir()` (줄 41): Claude Code SDK 작업 디렉토리 (메인 봇과 동일)
