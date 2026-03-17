# handlers/commands.py

> 경로: `seosoyoung/slackbot/handlers/commands.py`

## 개요

명령어 핸들러 모듈

mention.py의 try_handle_command에서 분리된 개별 명령어 핸들러들을 제공합니다.
각 핸들러는 keyword-only 인자를 받고, 사용하지 않는 인자는 **_로 흡수합니다.

## 함수

### `get_ancestors(pid)`
- 위치: 줄 26
- 설명: PID의 조상 체인(ancestor chain)을 반환

### `format_elapsed(elapsed_secs)`
- 위치: 줄 40
- 설명: 경과 시간을 사람이 읽기 쉬운 형태로 포맷

### `_collect_all_processes()`
- 위치: 줄 50
- 설명: 모든 프로세스의 기본 정보(pid, name, ppid, create_time)를 수집

### `_collect_claude_processes()`
- 위치: 줄 65
- 설명: Claude/node 관련 프로세스의 상세 정보를 수집

### `_classify_processes(claude_processes, all_processes)`
- 위치: 줄 109
- 설명: 프로세스를 봇 트리와 고아로 분류하여 (bot_tree, orphan_processes) 반환

### `_format_mem_size(mb)`
- 위치: 줄 154
- 설명: 메모리 크기를 사람이 읽기 쉬운 형태로 포맷

### `handle_help()`
- 위치: 줄 164
- 설명: help 명령어 핸들러

### `handle_status()`
- 위치: 줄 187
- 설명: status 명령어 핸들러 - 시스템 상태 및 프로세스 트리 표시

### `handle_cleanup()`
- 위치: 줄 239
- 설명: cleanup 명령어 핸들러 - 고아 프로세스 및 오래된 세션 정리

### `_collect_old_sessions(session_manager, threshold_hours)`
- 위치: 줄 277
- 설명: 오래된 세션(threshold_hours 이상)을 식별하여 반환

### `_format_cleanup_preview(orphan_processes, old_sessions, mem_str)`
- 위치: 줄 296
- 설명: cleanup dry-run 결과 메시지 포맷

### `_terminate_processes(orphan_processes)`
- 위치: 줄 326
- 설명: 고아 프로세스를 종료하고 (terminated_lines, failed_lines, reclaimed_mb) 반환

### `_format_cleanup_result(terminated_lines, failed_lines, reclaimed_mem_mb, cleaned_session_count, session_manager)`
- 위치: 줄 351
- 설명: cleanup confirm 결과 메시지 포맷

### `handle_log()`
- 위치: 줄 387
- 설명: log 명령어 핸들러 - 오늘자 로그 파일 첨부

### `handle_translate()`
- 위치: 줄 423
- 설명: 번역 명령어 핸들러

TranslatePlugin의 설정과 translate_text() 메서드를 사용합니다.

### `handle_update_restart()`
- 위치: 줄 466
- 설명: update/restart 명령어 핸들러

### `handle_compact()`
- 위치: 줄 520
- 설명: compact 명령어 핸들러 - Soulstream 서비스에 compact 요청

### `_run_soul_api(async_fn)`
- 위치: 줄 566
- 설명: SoulServiceClient API를 동기적으로 호출

slack_bolt sync mode에서 핸들러 스레드에는 이벤트 루프가 없으므로
asyncio.run()으로 새 루프를 생성하여 호출합니다.

Args:
    async_fn: SoulServiceClient 인스턴스를 받아 코루틴을 반환하는 함수

Returns:
    API 응답

### `_sanitize_email_to_profile_name(email)`
- 위치: 줄 593
- 설명: 이메일에서 프로필 이름 생성

user@example.com → user
유효하지 않은 문자는 언더스코어로 대체하고, 최대 64자로 제한합니다.

Args:
    email: 이메일 주소

Returns:
    프로필 이름으로 사용 가능한 문자열

### `_fetch_profiles_with_rates()`
- 위치: 줄 614
- 설명: Soulstream API에서 프로필 목록 + rate limit을 조회하여 병합.

Returns:
    (active: str, merged_profiles: list[dict])
    - active: 현재 활성 프로필 이름 (없으면 "")
    - merged_profiles: rate limit 정보가 병합된 프로필 리스트

### `_handle_profile_list(say, reply_ts)`
- 위치: 줄 649
- 설명: profile list: Soulstream API로 프로필 + rate limit 조회 후 게이지 바 UI 표시

### `_handle_profile_delete_ui(say, reply_ts)`
- 위치: 줄 675
- 설명: profile delete (이름 미입력): 프로필 목록을 삭제 버튼으로 표시

### `handle_profile()`
- 위치: 줄 708
- 설명: profile 명령어 핸들러 - Soulstream API 기반 인증 프로필 관리

### `handle_plugins()`
- 위치: 줄 791
- 설명: plugins 명령어 핸들러 — 플러그인 목록/로드/언로드/리로드

### `handle_resume_list_run()`
- 위치: 줄 862
- 설명: 정주행 재개 명령어 핸들러

### `handle_set_token()`
- 위치: 줄 890
- 설명: set-token 명령어 핸들러 - Claude OAuth 토큰 설정

사용법: @서소영 set-token sk-ant-oat01-xxx

### `handle_clear_token()`
- 위치: 줄 942
- 설명: clear-token 명령어 핸들러 - Claude OAuth 토큰 삭제

사용법: @서소영 clear-token

### `handle_session_info()`
- 위치: 줄 970
- 설명: session-info 명령어 핸들러 - 현재 스레드의 세션 정보 표시

디버깅용으로, 현재 스레드에 연결된 세션의 주요 ID들을 표시합니다.
스레드 안에서 실행해야 의미 있는 결과를 얻을 수 있습니다.

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.restart.RestartRequest`
- `seosoyoung.slackbot.restart.RestartType`
- `seosoyoung.slackbot.slack.formatting.update_message`
- `seosoyoung.slackbot.slack.helpers.resolve_operator_dm`
