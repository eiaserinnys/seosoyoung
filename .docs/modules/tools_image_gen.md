# tools/image_gen.py

> 경로: `seosoyoung/mcp/tools/image_gen.py`

## 개요

이미지 생성 및 슬랙 업로드 MCP 도구

## 함수

### `async generate_and_upload_image(prompt, channel, thread_ts, reference_image_paths)`
- 위치: 줄 15
- 설명: 이미지를 생성하고 슬랙 스레드에 업로드

Args:
    prompt: 이미지 생성 프롬프트
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프
    reference_image_paths: 레퍼런스 이미지 절대 경로 (쉼표 구분, 선택)

Returns:
    dict: success, message, file_name(성공 시) 키를 포함하는 결과

## 내부 의존성

- `seosoyoung.image_gen.generate_image`
- `seosoyoung.mcp.config.SLACK_BOT_TOKEN`
