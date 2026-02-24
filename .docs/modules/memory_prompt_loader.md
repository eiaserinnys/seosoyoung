# memory/prompt_loader.py

> 경로: `seosoyoung/slackbot/memory/prompt_loader.py`

## 개요

프롬프트 파일 로더

외부 텍스트 파일에서 프롬프트를 로드합니다.

검색 순서:
1. 환경변수로 지정된 개별 파일 (OM_PROMPT_DIR / CHANNEL_PROMPT_DIR)
2. 환경변수로 지정된 공통 디렉토리 (PROMPT_FILES_DIR)
3. 배포본 기본 경로 (memory/prompt_files/)

비워두거나 미설정하면 배포본에 포함된 기본 경로를 사용합니다.

## 함수

### `_resolve_prompt_path(filename)`
- 위치: 줄 32
- 설명: 프롬프트 파일의 실제 경로를 결정합니다.

검색 순서:
1. 파일명 접두사에 따른 개별 디렉토리 환경변수
2. 공통 디렉토리 환경변수 (PROMPT_FILES_DIR)
3. 배포본 기본 경로

Args:
    filename: 프롬프트 파일명

Returns:
    해결된 파일 경로

### `load_prompt(filename)`
- 위치: 줄 71
- 설명: 프롬프트 파일을 로드합니다.

Args:
    filename: 프롬프트 파일명

Returns:
    프롬프트 텍스트

Raises:
    FileNotFoundError: 파일이 존재하지 않을 때

### `load_prompt_cached(filename)`
- 위치: 줄 90
- 데코레이터: lru_cache
- 설명: 프롬프트 파일을 캐시하여 로드합니다.

프로세스 수명 동안 한 번만 파일을 읽습니다.
프롬프트 파일이 변경되면 프로세스를 재시작해야 합니다.

Args:
    filename: 프롬프트 파일명

Returns:
    프롬프트 텍스트
