# claude/diagnostics.py

> 경로: `seosoyoung/slackbot/claude/diagnostics.py`

## 개요

세션 진단 및 에러 분류 로직

agent_runner.py에서 분리된 진단 전용 모듈.
ProcessError 분류, 세션 덤프 생성, stderr 캡처 등을 담당합니다.

## 함수

### `read_stderr_tail(n_lines)`
- 위치: 줄 17
- 설명: 세션별 cli_stderr 로그의 마지막 N줄 읽기

세션별 파일(cli_stderr_{thread_ts}.log)을 우선 시도하고,
없으면 공유 파일(cli_stderr.log)로 폴백합니다.

Args:
    n_lines: 읽을 줄 수
    thread_ts: 스레드 타임스탬프 (None이면 "default" 사용)

### `build_session_dump()`
- 위치: 줄 50
- 설명: 세션 종료 진단 덤프 메시지 생성

Args:
    thread_ts: 스레드 타임스탬프 (세션별 stderr 파일 식별용)

### `classify_process_error(e)`
- 위치: 줄 95
- 설명: ProcessError를 사용자 친화적 메시지로 변환.

Claude Code CLI는 다양한 이유로 exit code 1을 반환하지만,
SDK가 stderr를 캡처하지 않아 원인 구분이 어렵습니다.
exit_code와 stderr 패턴을 기반으로 최대한 분류합니다.

### `format_rate_limit_warning(rate_limit_info)`
- 위치: 줄 135
- 설명: allowed_warning용 사람이 읽을 수 있는 안내문 생성.

Args:
    rate_limit_info: rate_limit_event의 rate_limit_info 딕셔너리

Returns:
    "⚠️ 주간 사용량 중 51%를 넘었습니다" 형태의 안내문

### `send_debug_to_slack(channel, thread_ts, message)`
- 위치: 줄 151
- 설명: 슬랙에 디버그 메시지 전송 (별도 메시지로)

### `_get_slack_client()`
- 위치: 줄 169
- 설명: 슬랙 클라이언트 가져오기 (lazy init)
