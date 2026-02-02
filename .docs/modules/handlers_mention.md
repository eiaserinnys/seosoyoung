# handlers/mention.py

> 경로: `seosoyoung/handlers/mention.py`

## 개요

@seosoyoung 멘션 핸들러

## 함수

### `_get_recall()`
- 위치: 줄 20
- 설명: Recall 싱글톤 반환 (지연 초기화)

### `_run_recall(user_request)`
- 위치: 줄 51
- 설명: Recall 실행 (동기 래퍼)

Args:
    user_request: 사용자 요청

Returns:
    RecallResult 또는 None

### `extract_command(text)`
- 위치: 줄 80
- 설명: 멘션에서 명령어 추출

### `_is_resume_list_run_command(command)`
- 위치: 줄 86
- 설명: 정주행 재개 명령어인지 확인

다음과 같은 패턴을 인식합니다:
- 정주행 재개해줘
- 정주행 재개
- 리스트런 재개
- resume list run

### `build_prompt_with_recall(context, question, file_context, recall_result)`
- 위치: 줄 106
- 설명: Recall 결과를 포함한 프롬프트 구성.

Args:
    context: 채널 히스토리 컨텍스트
    question: 사용자 질문
    file_context: 첨부 파일 컨텍스트
    recall_result: RecallResult 객체 (선택사항)

Returns:
    구성된 프롬프트 문자열

### `get_channel_history(client, channel, limit)`
- 위치: 줄 142
- 설명: 채널의 최근 메시지를 가져와서 컨텍스트 문자열로 반환

### `register_mention_handlers(app, dependencies)`
- 위치: 줄 163
- 설명: 멘션 핸들러 등록

Args:
    app: Slack Bolt App 인스턴스
    dependencies: 의존성 딕셔너리

## 내부 의존성

- `seosoyoung.config.Config`
- `seosoyoung.restart.RestartType`
- `seosoyoung.slack.build_file_context`
- `seosoyoung.slack.download_files_sync`
- `seosoyoung.translator.detect_language`
- `seosoyoung.translator.translate`
