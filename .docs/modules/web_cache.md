# web/cache.py

> 경로: `seosoyoung/slackbot/web/cache.py`

## 개요

웹 콘텐츠 캐시 관리

## 클래스

### `WebCache`
- 위치: 줄 10
- 설명: URL 기반 웹 콘텐츠 캐시 관리자

#### 메서드

- `__init__(self, cache_dir)` (줄 13): Args:
- `get_cache_file_path(self, url)` (줄 20): URL에 해당하는 캐시 파일 경로 반환
- `_ensure_dir(self)` (줄 32): 캐시 디렉토리가 없으면 생성
- `save(self, url, data)` (줄 36): 캐시 데이터 저장
- `load(self, url)` (줄 48): 캐시 데이터 로드
- `exists(self, url)` (줄 63): 캐시 존재 여부 확인
- `delete(self, url)` (줄 74): 캐시 삭제
