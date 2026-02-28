# handlers/commands.py

> 경로: `seosoyoung/slackbot/handlers/commands.py`

## 개요

명령어 핸들러 모듈

mention.py의 try_handle_command에서 분리된 개별 명령어 핸들러들을 제공합니다.
각 핸들러는 keyword-only 인자를 받고, 사용하지 않는 인자는 **_로 흡수합니다.

## 함수

### `get_ancestors(pid)`
- 위치: 줄 24
- 설명: PID의 조상 체인(ancestor chain)을 반환

### `format_elapsed(elapsed_secs)`
- 위치: 줄 38
- 설명: 경과 시간을 사람이 읽기 쉬운 형태로 포맷

### `_collect_all_processes()`
- 위치: 줄 48
- 설명: 모든 프로세스의 기본 정보(pid, name, ppid, create_time)를 수집

### `_collect_claude_processes()`
- 위치: 줄 63
- 설명: Claude/node 관련 프로세스의 상세 정보를 수집

### `_classify_processes(claude_processes, all_processes)`
- 위치: 줄 107
- 설명: 프로세스를 봇 트리와 고아로 분류하여 (bot_tree, orphan_processes) 반환

### `_format_mem_size(mb)`
- 위치: 줄 152
- 설명: 메모리 크기를 사람이 읽기 쉬운 형태로 포맷

### `handle_help()`
- 위치: 줄 162
- 설명: help 명령어 핸들러

### `handle_status()`
- 위치: 줄 182
- 설명: status 명령어 핸들러 - 시스템 상태 및 프로세스 트리 표시

### `handle_cleanup()`
- 위치: 줄 234
- 설명: cleanup 명령어 핸들러 - 고아 프로세스 및 오래된 세션 정리

### `_collect_old_sessions(session_manager, threshold_hours)`
- 위치: 줄 272
- 설명: 오래된 세션(threshold_hours 이상)을 식별하여 반환

### `_format_cleanup_preview(orphan_processes, old_sessions, mem_str)`
- 위치: 줄 291
- 설명: cleanup dry-run 결과 메시지 포맷

### `_terminate_processes(orphan_processes)`
- 위치: 줄 321
- 설명: 고아 프로세스를 종료하고 (terminated_lines, failed_lines, reclaimed_mb) 반환

### `_format_cleanup_result(terminated_lines, failed_lines, reclaimed_mem_mb, cleaned_session_count, session_manager)`
- 위치: 줄 346
- 설명: cleanup confirm 결과 메시지 포맷

### `handle_log()`
- 위치: 줄 382
- 설명: log 명령어 핸들러 - 오늘자 로그 파일 첨부

### `handle_translate()`
- 위치: 줄 418
- 설명: 번역 명령어 핸들러

### `handle_update_restart()`
- 위치: 줄 456
- 설명: update/restart 명령어 핸들러

### `handle_compact()`
- 위치: 줄 494
- 설명: compact 명령어 핸들러 - 안내 메시지

### `_run_soul_profile_api(async_fn)`
- 위치: 줄 506
- 설명: SoulServiceClient 프로필 API를 동기적으로 호출

slack_bolt sync mode에서 핸들러 스레드에는 이벤트 루프가 없으므로
asyncio.run()으로 새 루프를 생성하여 호출합니다.

Args:
    async_fn: SoulServiceClient 인스턴스를 받아 코루틴을 반환하는 함수

Returns:
    API 응답 딕셔너리

### `_handle_profile_list(say, reply_ts)`
- 위치: 줄 533
- 설명: profile list: Soulstream API로 프로필 + rate limit 조회 후 게이지 바 UI 표시

### `handle_profile()`
- 위치: 줄 602
- 설명: profile 명령어 핸들러 - Soulstream API 기반 인증 프로필 관리

### `handle_resume_list_run()`
- 위치: 줄 653
- 설명: 정주행 재개 명령어 핸들러

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.restart.RestartType`
