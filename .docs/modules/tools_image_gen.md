# tools/image_gen.py

> 경로: `seosoyoung/mcp/tools/image_gen.py`

## 개요

이미지 생성 및 슬랙 업로드 MCP 도구

Gemini API를 호출하여 이미지를 생성하고, 슬랙 스레드에 업로드합니다.
레퍼런스 이미지를 함께 전달하면 multimodal input으로 처리합니다.

## 클래스

### `GeneratedImage`
- 위치: 줄 42
- 설명: 생성된 이미지 결과

## 함수

### `_load_reference_images(paths)`
- 위치: 줄 49
- 설명: 레퍼런스 이미지 경로들을 Gemini Part 객체로 변환

### `async generate_image(prompt, model, reference_images, image_size, aspect_ratio)`
- 위치: 줄 67
- 설명: Gemini API로 이미지를 생성하고 임시 파일로 저장

Args:
    prompt: 이미지 생성 프롬프트
    model: 사용할 모델 (None이면 Config.gemini.model 사용)
    reference_images: 레퍼런스 이미지 파일 경로 목록 (선택)
    image_size: 이미지 해상도 ("512px", "1K", "2K", "4K") (선택)
    aspect_ratio: 종횡비 ("1:1", "16:9", "9:16" 등) (선택)

Returns:
    GeneratedImage: 생성된 이미지 정보

Raises:
    ValueError: API 키가 설정되지 않은 경우, 또는 잘못된 파라미터
    RuntimeError: 이미지 생성에 실패한 경우

### `async generate_and_upload_image(prompt, channel, thread_ts, reference_image_paths, image_size, aspect_ratio)`
- 위치: 줄 173
- 설명: 이미지를 생성하고 슬랙 스레드에 업로드

Args:
    prompt: 이미지 생성 프롬프트
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프
    reference_image_paths: 레퍼런스 이미지 절대 경로 (쉼표 구분, 선택)
    image_size: 이미지 해상도 ("512px", "1K", "2K", "4K") (선택)
    aspect_ratio: 종횡비 ("1:1", "16:9", "9:16" 등) (선택)

Returns:
    dict: success, message, file_name(성공 시) 키를 포함하는 결과

## 내부 의존성

- `seosoyoung.mcp.config.SLACK_BOT_TOKEN`
- `seosoyoung.slackbot.config.Config`
