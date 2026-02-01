# handlers/mention.py

> 경로: `seosoyoung/handlers/mention.py`

## 개요

@seosoyoung 멘션 핸들러

## 함수

### `extract_command(text)`
- 위치: 줄 15
- 설명: 멘션에서 명령어 추출

### `_is_resume_list_run_command(command)`
- 위치: 줄 21
- 설명: 정주행 재개 명령어인지 확인

다음과 같은 패턴을 인식합니다:
- 정주행 재개해줘
- 정주행 재개
- 리스트런 재개
- resume list run

### `build_prompt_with_routing(context, question, file_context, routing_result)`
- 위치: 줄 41
- 설명: 라우팅 결과를 포함한 프롬프트 구성.

Args:
    context: 채널 히스토리 컨텍스트
    question: 사용자 질문
    file_context: 첨부 파일 컨텍스트
    routing_result: RoutingResult 객체 (선택사항)

Returns:
    구성된 프롬프트 문자열

### `get_channel_history(client, channel, limit)`
- 위치: 줄 77
- 설명: 채널의 최근 메시지를 가져와서 컨텍스트 문자열로 반환

### `register_mention_handlers(app, dependencies)`
- 위치: 줄 98
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
