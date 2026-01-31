# seosoyoung 코드 인덱스

> 이 문서는 자동 생성되었습니다. 직접 수정하지 마세요.
> 생성 명령: `python .docs/generate.py`

## 모듈 목록

- [`seosoyoung/auth.py`](modules/seosoyoung_auth.md): 권한 및 역할 관리
- [`claude/agent_runner.py`](modules/claude_agent_runner.md): Claude Code SDK 기반 실행기
- [`claude/executor.py`](modules/claude_executor.md): Claude Code 실행 로직
- [`claude/runner.py`](modules/claude_runner.md): Claude Code CLI 래퍼
- [`claude/security.py`](modules/claude_security.md): 보안 레이어
- [`claude/session.py`](modules/claude_session.md): Claude Code 세션 관리
- [`seosoyoung/config.py`](modules/seosoyoung_config.md): 설정 관리
- [`handlers/actions.py`](modules/handlers_actions.md): 재시작 버튼 액션 핸들러
- [`handlers/mention.py`](modules/handlers_mention.md): @seosoyoung 멘션 핸들러
- [`handlers/message.py`](modules/handlers_message.md): 스레드 메시지 핸들러
- [`handlers/translate.py`](modules/handlers_translate.md): 번역 핸들러
- [`seosoyoung/logging_config.py`](modules/seosoyoung_logging_config.md): 로깅 설정 모듈
- [`seosoyoung/main.py`](modules/seosoyoung_main.md): SeoSoyoung 슬랙 봇 메인
- [`seosoyoung/restart.py`](modules/seosoyoung_restart.md): 재시작 관리
- [`search/schema.py`](modules/search_schema.md): Whoosh schema definition for dialogue search.
- [`search/searcher.py`](modules/search_searcher.md): Whoosh searcher for dialogue data.
- [`slack/file_handler.py`](modules/slack_file_handler.md): 슬랙 파일 다운로드 및 처리 유틸리티
- [`slack/helpers.py`](modules/slack_helpers.md): Slack 메시지 유틸리티
- [`translator/__main__.py`](modules/translator___main__.md): 번역 기능 CLI 테스트
- [`translator/detector.py`](modules/translator_detector.md): 언어 감지 모듈
- [`translator/glossary.py`](modules/translator_glossary.md): 용어집 로더 모듈
- [`translator/translator.py`](modules/translator_translator.md): 번역 모듈
- [`trello/client.py`](modules/trello_client.md): Trello API 클라이언트
- [`trello/list_runner.py`](modules/trello_list_runner.md): ListRunner - 리스트 정주행 기능
- [`trello/watcher.py`](modules/trello_watcher.md): Trello 워처 - To Go 리스트 감시 및 처리
- [`web/cache.py`](modules/web_cache.md): 웹 콘텐츠 캐시 관리

## 빠른 참조

### 주요 클래스

- `ClaudeResult` (seosoyoung/claude/agent_runner.py:42): Claude Code 실행 결과
- `ClaudeAgentRunner` (seosoyoung/claude/agent_runner.py:54): Claude Code SDK 기반 실행기
- `ClaudeExecutor` (seosoyoung/claude/executor.py:168): Claude Code 실행기
- `ClaudeResult` (seosoyoung/claude/runner.py:43): Claude Code 실행 결과
- `ClaudeRunner` (seosoyoung/claude/runner.py:56): Claude Code CLI 실행기
- `SecurityError` (seosoyoung/claude/security.py:10): 보안 관련 에러
- `Session` (seosoyoung/claude/session.py:21): Claude Code 세션 정보
- `SessionManager` (seosoyoung/claude/session.py:41): 세션 매니저
- `SessionRuntime` (seosoyoung/claude/session.py:185): 세션 실행 상태 관리자
- `Config` (seosoyoung/config.py:18): 
- `RestartType` (seosoyoung/restart.py:15): 재시작 유형
- `RestartRequest` (seosoyoung/restart.py:22): 재시작 요청 정보
- `RestartManager` (seosoyoung/restart.py:30): 재시작 관리자
- `DialogueSearcher` (seosoyoung/search/searcher.py:14): 대사 검색 API.
- `SlackFile` (seosoyoung/slack/file_handler.py:35): 슬랙 파일 정보
- `DownloadedFile` (seosoyoung/slack/file_handler.py:45): 다운로드된 파일 정보
- `Language` (seosoyoung/translator/detector.py:9): 
- `GlossaryMatchResult` (seosoyoung/translator/glossary.py:43): 용어 매칭 결과
- `TrelloCard` (seosoyoung/trello/client.py:16): 트렐로 카드 정보
- `TrelloClient` (seosoyoung/trello/client.py:28): Trello API 클라이언트
- `ListNotFoundError` (seosoyoung/trello/list_runner.py:20): 리스트를 찾을 수 없을 때 발생하는 예외
- `EmptyListError` (seosoyoung/trello/list_runner.py:25): 리스트에 카드가 없을 때 발생하는 예외
- `ValidationStatus` (seosoyoung/trello/list_runner.py:30): 검증 결과 상태
- `SessionStatus` (seosoyoung/trello/list_runner.py:37): 리스트 정주행 세션 상태
- `CardExecutionResult` (seosoyoung/trello/list_runner.py:48): 카드 실행 결과
- `ValidationResult` (seosoyoung/trello/list_runner.py:58): 검증 결과
- `CardRunResult` (seosoyoung/trello/list_runner.py:67): 카드 실행 및 검증 전체 결과
- `ListRunSession` (seosoyoung/trello/list_runner.py:78): 리스트 정주행 세션 정보
- `ListRunner` (seosoyoung/trello/list_runner.py:123): 리스트 정주행 관리자
- `TrackedCard` (seosoyoung/trello/watcher.py:19): 추적 중인 카드 정보 (To Go 리스트 감시용)
- `ThreadCardInfo` (seosoyoung/trello/watcher.py:34): 스레드 ↔ 카드 매핑 정보 (리액션 처리용)
- `TrelloWatcher` (seosoyoung/trello/watcher.py:50): Trello 리스트 감시자
- `WebCache` (seosoyoung/web/cache.py:10): URL 기반 웹 콘텐츠 캐시 관리자

### 주요 함수

- `check_permission()` (seosoyoung/auth.py:13): 사용자 권한 확인 (관리자 명령어용)
- `get_user_role()` (seosoyoung/auth.py:26): 사용자 역할 정보 반환
- `get_claude_runner()` (seosoyoung/claude/__init__.py:15): Claude 실행기 인스턴스를 반환하는 팩토리 함수
- `async main()` (seosoyoung/claude/agent_runner.py:223): 
- `get_runner_for_role()` (seosoyoung/claude/executor.py:20): 역할에 맞는 ClaudeRunner/ClaudeAgentRunner 반환
- `async main()` (seosoyoung/claude/runner.py:462): 
- `register_all_handlers()` (seosoyoung/handlers/__init__.py:9): 모든 핸들러를 앱에 등록
- `send_restart_confirmation()` (seosoyoung/handlers/actions.py:11): 재시작 확인 메시지를 인터랙티브 버튼과 함께 전송
- `register_action_handlers()` (seosoyoung/handlers/actions.py:79): 액션 핸들러 등록
- `extract_command()` (seosoyoung/handlers/mention.py:15): 멘션에서 명령어 추출
- `get_channel_history()` (seosoyoung/handlers/mention.py:41): 채널의 최근 메시지를 가져와서 컨텍스트 문자열로 반환
- `register_mention_handlers()` (seosoyoung/handlers/mention.py:62): 멘션 핸들러 등록
- `register_message_handlers()` (seosoyoung/handlers/message.py:24): 메시지 핸들러 등록
- `process_translate_message()` (seosoyoung/handlers/translate.py:194): 메시지를 번역 처리합니다.
- `register_translate_handler()` (seosoyoung/handlers/translate.py:319): 번역 핸들러를 앱에 등록합니다.
- `setup_logging()` (seosoyoung/logging_config.py:10): 로깅 설정 및 로거 반환
- `notify_startup()` (seosoyoung/main.py:92): 봇 시작 알림
- `notify_shutdown()` (seosoyoung/main.py:103): 봇 종료 알림
- `start_trello_watcher()` (seosoyoung/main.py:114): Trello 워처 시작
- `start_list_runner()` (seosoyoung/main.py:133): 리스트 러너 초기화
- `init_bot_user_id()` (seosoyoung/main.py:143): 봇 사용자 ID 초기화
- `get_default_index_path()` (seosoyoung/search/searcher.py:197): 기본 인덱스 경로 반환.
- `format_results()` (seosoyoung/search/searcher.py:202): 결과 포맷팅.
- `main()` (seosoyoung/search/searcher.py:222): CLI 진입점.
- `get_file_type()` (seosoyoung/slack/file_handler.py:54): 파일 확장자로 타입 분류
- `ensure_tmp_dir()` (seosoyoung/slack/file_handler.py:67): 스레드별 임시 폴더 생성
- `cleanup_thread_files()` (seosoyoung/slack/file_handler.py:76): 스레드의 임시 파일 정리
- `cleanup_all_files()` (seosoyoung/slack/file_handler.py:88): 모든 임시 파일 정리
- `async download_file()` (seosoyoung/slack/file_handler.py:98): 슬랙 파일 다운로드
- `async download_files_from_event()` (seosoyoung/slack/file_handler.py:183): 이벤트에서 파일들을 다운로드 (async 버전)
- `download_files_sync()` (seosoyoung/slack/file_handler.py:209): 이벤트에서 파일들을 다운로드 (동기 버전)
- `build_file_context()` (seosoyoung/slack/file_handler.py:240): 파일 정보를 프롬프트 컨텍스트로 구성
- `upload_file_to_slack()` (seosoyoung/slack/helpers.py:12): 파일을 슬랙에 첨부
- `send_long_message()` (seosoyoung/slack/helpers.py:47): 긴 메시지를 분할해서 전송 (thread_ts가 None이면 채널에 응답)
- `main()` (seosoyoung/translator/__main__.py:18): 
- `is_korean_char()` (seosoyoung/translator/detector.py:14): 한글 문자인지 확인 (한글 자모, 음절 모두 포함)
- `detect_language()` (seosoyoung/translator/detector.py:27): 텍스트의 언어를 감지
- `get_glossary_entries()` (seosoyoung/translator/glossary.py:135): 용어집 항목들을 (한국어, 영어) 쌍으로 반환 (캐싱)
- `find_relevant_terms()` (seosoyoung/translator/glossary.py:268): 텍스트에서 관련 용어 추출 (하위 호환성 유지)
- `find_relevant_terms_v2()` (seosoyoung/translator/glossary.py:287): 텍스트에서 관련 용어 추출 (개선된 버전, 디버그 정보 포함)
- `get_term_mappings()` (seosoyoung/translator/glossary.py:403): 용어 매핑 딕셔너리 생성 (하위 호환성 유지)
- `clear_cache()` (seosoyoung/translator/glossary.py:433): 캐시 초기화 (테스트 또는 용어집 갱신 시 사용)
- `translate()` (seosoyoung/translator/translator.py:125): 텍스트를 번역