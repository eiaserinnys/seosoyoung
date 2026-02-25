# rescue/main.py

> 경로: `seosoyoung/rescue/main.py`

## 개요

rescue-bot 메인 모듈 (메인 봇 기본 대화 기능 완전 복제)

슬랙 멘션/스레드 메시지 → Claude Code SDK 직접 호출 → 결과 응답
soul 서버를 경유하지 않는 독립 경량 봇입니다.

메인 봇에서 복제한 기능:
- SessionManager 기반 세션 관리
- 인터벤션 (interrupt → pending prompt → while loop)
- on_progress 사고 과정 표시
- on_compact 컴팩션 알림
- help/status/compact 명령어
- 슬랙 컨텍스트 블록 (채널/스레드/파일 정보)
- 긴 메시지 분할 전송

제외 기능:
- OM, Recall, 트렐로 연동, 번역, 채널 관찰
- 프로필 관리, 정주행, NPC 대화, Remote 모드

## 클래스

### `PendingPrompt`
- 위치: 줄 75
- 설명: 인터벤션 대기 중인 프롬프트 정보

### `RescueBotApp`
- 위치: 줄 84
- 설명: rescue-bot 애플리케이션

메인 봇의 ClaudeExecutor + 핸들러를 하나의 클래스로 통합한 경량 버전.

#### 메서드

- `__init__(self)` (줄 90): 
- `_get_or_create_session(self, thread_ts, channel)` (줄 111): 세션 조회, 없으면 생성
- `_get_session(self, thread_ts)` (줄 115): 세션 조회
- `_get_thread_lock(self, thread_ts)` (줄 121): 스레드별 락을 가져오거나 생성
- `_extract_command(self, text)` (줄 130): 멘션에서 명령어 추출
- `_strip_mention(self, text)` (줄 135): 멘션 태그를 제거하고 순수 텍스트만 반환
- `_contains_bot_mention(self, text)` (줄 142): 텍스트에 봇 멘션이 포함되어 있는지 확인
- `_should_ignore_event(self, event)` (줄 148): 무시해야 할 이벤트인지 판단
- `_build_slack_context(self, channel, user_id, thread_ts)` (줄 158): 슬랙 컨텍스트 블록 생성
- `_send_long_message(self, say, text, thread_ts)` (줄 176): 긴 메시지를 3900자 단위로 분할하여 전송
- `_pop_pending(self, thread_ts)` (줄 186): pending 프롬프트를 꺼내고 제거
- `_handle_intervention(self, thread_ts, prompt, msg_ts, channel, say, client)` (줄 191): 인터벤션 처리: 실행 중인 스레드에 새 메시지가 도착한 경우
- `_process_message(self, prompt, thread_ts, channel, user_id, say, client, is_thread_reply)` (줄 227): 공통 메시지 처리 로직 (인터벤션 지원)
- `_run_with_lock(self, prompt, thread_ts, channel, user_id, say, client, is_thread_reply)` (줄 254): 락을 보유한 상태에서 실행 (while 루프로 pending 처리)
- `_execute_once(self, prompt, thread_ts, channel, user_id, say, client, is_thread_reply)` (줄 284): 단일 Claude 실행
- `_handle_interrupted(self, last_msg_ts, channel, client)` (줄 391): 인터럽트로 중단된 실행의 사고 과정 메시지 정리
- `_handle_success(self, result, channel, thread_ts, last_msg_ts, say, client, is_thread_reply)` (줄 399): 성공 결과 처리
- `_handle_error(self, error, channel, thread_ts, last_msg_ts, say, client, is_thread_reply)` (줄 466): 오류 결과 처리
- `_handle_help(self, say, thread_ts)` (줄 491): help 명령어
- `_handle_status(self, say, thread_ts)` (줄 504): status 명령어
- `_handle_compact(self, say, client, thread_ts, parent_thread_ts)` (줄 515): compact 명령어
- `handle_mention(self, event, say, client)` (줄 545): 멘션 이벤트 핸들러
- `handle_message(self, event, say, client)` (줄 599): 스레드 메시지 핸들러

## 함수

### `_ensure_sdk_installed()`
- 위치: 줄 21
- 설명: claude-agent-sdk가 없으면 자동 설치 시도

### `main()`
- 위치: 줄 641
- 설명: rescue-bot 진입점

## 내부 의존성

- `seosoyoung.rescue.config.RescueConfig`
- `seosoyoung.rescue.message_formatter.build_context_usage_bar`
- `seosoyoung.rescue.message_formatter.escape_backticks`
- `seosoyoung.rescue.runner.RescueResult`
- `seosoyoung.rescue.runner.get_runner`
- `seosoyoung.rescue.session.Session`
- `seosoyoung.rescue.session.SessionManager`
- `seosoyoung.slackbot.slack.formatting.update_message`
