# image_gen/generator.py

> 경로: `seosoyoung/image_gen/generator.py`

## 개요

Gemini API 이미지 생성 모듈

텍스트 프롬프트로 Gemini API를 호출하여 이미지를 생성하고 임시 파일로 저장합니다.

## 클래스

### `GeneratedImage`
- 위치: 줄 24
- 설명: 생성된 이미지 결과

## 함수

### `async generate_image(prompt, model)`
- 위치: 줄 31
- 설명: Gemini API로 이미지를 생성하고 임시 파일로 저장

Args:
    prompt: 이미지 생성 프롬프트
    model: 사용할 모델 (None이면 Config.GEMINI_MODEL 사용)

Returns:
    GeneratedImage: 생성된 이미지 정보

Raises:
    ValueError: API 키가 설정되지 않은 경우
    RuntimeError: 이미지 생성에 실패한 경우

## 내부 의존성

- `seosoyoung.config.Config`
