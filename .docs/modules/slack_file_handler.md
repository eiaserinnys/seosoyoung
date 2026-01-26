# slack/file_handler.py

> 경로: `seosoyoung/slack/file_handler.py`

## 개요

슬랙 파일 다운로드 및 처리 유틸리티

슬랙에 첨부된 파일을 다운로드하여 Claude Code에 전달할 수 있도록 처리합니다.

## 클래스

### `SlackFile` (TypedDict)
- 위치: 줄 35
- 설명: 슬랙 파일 정보

### `DownloadedFile` (TypedDict)
- 위치: 줄 45
- 설명: 다운로드된 파일 정보

## 함수

### `get_file_type(filename)`
- 위치: 줄 54
- 설명: 파일 확장자로 타입 분류

### `ensure_tmp_dir(thread_ts)`
- 위치: 줄 67
- 설명: 스레드별 임시 폴더 생성

### `cleanup_thread_files(thread_ts)`
- 위치: 줄 76
- 설명: 스레드의 임시 파일 정리

### `cleanup_all_files()`
- 위치: 줄 88
- 설명: 모든 임시 파일 정리

### `async download_file(file_info, thread_ts)`
- 위치: 줄 98
- 설명: 슬랙 파일 다운로드

Args:
    file_info: 슬랙 파일 정보 (event["files"]의 각 항목)
    thread_ts: 스레드 타임스탬프

Returns:
    DownloadedFile 또는 None (실패 시)

### `async download_files_from_event(event, thread_ts)`
- 위치: 줄 183
- 설명: 이벤트에서 파일들을 다운로드 (async 버전)

Args:
    event: 슬랙 이벤트 (app_mention 또는 message)
    thread_ts: 스레드 타임스탬프

Returns:
    다운로드된 파일 목록

### `download_files_sync(event, thread_ts)`
- 위치: 줄 209
- 설명: 이벤트에서 파일들을 다운로드 (동기 버전)

ThreadPoolExecutor 환경(Slack Bolt 핸들러)에서 안전하게 사용할 수 있습니다.
새 이벤트 루프를 생성하여 async 함수를 실행합니다.

Args:
    event: 슬랙 이벤트 (app_mention 또는 message)
    thread_ts: 스레드 타임스탬프

Returns:
    다운로드된 파일 목록

### `build_file_context(files)`
- 위치: 줄 240
- 설명: 파일 정보를 프롬프트 컨텍스트로 구성

Args:
    files: 다운로드된 파일 목록

Returns:
    프롬프트에 추가할 파일 컨텍스트 문자열

## 내부 의존성

- `seosoyoung.config.Config`
