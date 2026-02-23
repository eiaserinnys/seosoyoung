# handlers/mention.py

> 경로: `seosoyoung/handlers/mention.py`

## 개요

@seosoyoung 멘션 핸들러

멘션 이벤트 처리 및 DM 채널에서 공유하는 명령어/세션 생성 함수를 제공합니다.

## 함수

### `_get_recall()`
- 위치: 줄 33
- 설명: Recall 싱글톤 반환 (지연 초기화)

### `_run_recall(user_request)`
- 위치: 줄 64
- 설명: Recall 실행 (동기 래퍼)

Args:
    user_request: 사용자 요청

Returns:
    RecallResult 또는 None

### `extract_command(text)`
- 위치: 줄 93
- 설명: 멘션에서 명령어 추출

### `_is_resume_list_run_command(command)`
- 위치: 줄 99
- 설명: 정주행 재개 명령어인지 확인

다음과 같은 패턴을 인식합니다:
- 정주행 재개해줘
- 정주행 재개
- 리스트런 재개
- resume list run

### `build_prompt_with_recall(context, question, file_context, recall_result, slack_context)`
- 위치: 줄 119
- 설명: Recall 결과를 포함한 프롬프트 구성.

Args:
    context: 채널 히스토리 컨텍스트
    question: 사용자 질문
    file_context: 첨부 파일 컨텍스트
    recall_result: RecallResult 객체 (선택사항)
    slack_context: 슬랙 컨텍스트 블록 문자열

Returns:
    구성된 프롬프트 문자열

### `_get_channel_messages(client, channel, limit)`
- 위치: 줄 163
- 설명: 채널의 최근 메시지를 가져와서 dict 리스트로 반환

### `_format_context_messages(messages)`
- 위치: 줄 175
- 설명: 메시지 dict 리스트를 컨텍스트 문자열로 포맷팅

### `get_channel_history(client, channel, limit)`
- 위치: 줄 185
- 설명: 채널의 최근 메시지를 가져와서 컨텍스트 문자열로 반환

### `_is_admin_command(command)`
- 위치: 줄 206
- 설명: 관리자 명령어 여부 판별

### `try_handle_command(command, text, channel, ts, thread_ts, user_id, say, client, deps)`
- 위치: 줄 215
- 설명: 명령어 라우팅. 처리했으면 True, 아니면 False 반환.

handle_mention과 DM 핸들러에서 공유합니다.

Args:
    command: 소문자로 정규화된 명령어 문자열
    text: 원본 텍스트 (번역용)
    channel: 채널 ID
    ts: 메시지 타임스탬프
    thread_ts: 스레드 타임스탬프 (없으면 None)
    user_id: 사용자 ID
    say: 응답 함수
    client: Slack 클라이언트
    deps: 의존성 딕셔너리

### `create_session_and_run_claude(event, clean_text, channel, ts, thread_ts, user_id, say, client, deps)`
- 위치: 줄 278
- 설명: 세션 생성 + 컨텍스트 빌드 + Claude 실행.

handle_mention과 DM 핸들러에서 공유합니다.

Args:
    event: Slack 이벤트 딕셔너리
    clean_text: 멘션이 제거된 깨끗한 텍스트
    channel: 채널 ID
    ts: 메시지 타임스탬프
    thread_ts: 스레드 타임스탬프 (없으면 None)
    user_id: 사용자 ID
    say: 응답 함수
    client: Slack 클라이언트
    deps: 의존성 딕셔너리

### `register_mention_handlers(app, dependencies)`
- 위치: 줄 423
- 설명: 멘션 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

## 내부 의존성

- `seosoyoung.claude.session_context.build_initial_context`
- `seosoyoung.claude.session_context.format_hybrid_context`
- `seosoyoung.config.Config`
- `seosoyoung.handlers.commands.handle_cleanup`
- `seosoyoung.handlers.commands.handle_compact`
- `seosoyoung.handlers.commands.handle_help`
- `seosoyoung.handlers.commands.handle_log`
- `seosoyoung.handlers.commands.handle_profile`
- `seosoyoung.handlers.commands.handle_resume_list_run`
- `seosoyoung.handlers.commands.handle_status`
- `seosoyoung.handlers.commands.handle_translate`
- `seosoyoung.handlers.commands.handle_update_restart`
- `seosoyoung.handlers.message.build_slack_context`
- `seosoyoung.handlers.message.process_thread_message`
- `seosoyoung.slack.build_file_context`
- `seosoyoung.slack.download_files_sync`
