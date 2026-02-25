# soul/config.py

> 경로: `seosoyoung/soul/config.py`

## 개요

Seosoyoung Soul - Configuration

환경변수 기반 설정 관리.

## 클래스

### `Settings`
- 위치: 줄 57
- 설명: 애플리케이션 설정

#### 메서드

- `from_env(cls)` (줄 95): 환경변수에서 설정 로드
- `is_production(self)` (줄 151): 
- `is_development(self)` (줄 155): 

## 함수

### `_safe_int(value, default, name)`
- 위치: 줄 20
- 설명: 환경변수를 안전하게 int로 변환

Args:
    value: 변환할 문자열
    default: 변환 실패 시 기본값
    name: 환경변수 이름 (로깅용)

Returns:
    변환된 int 값 또는 기본값

### `_safe_float(value, default, name)`
- 위치: 줄 38
- 설명: 환경변수를 안전하게 float로 변환

Args:
    value: 변환할 문자열
    default: 변환 실패 시 기본값
    name: 환경변수 이름 (로깅용)

Returns:
    변환된 float 값 또는 기본값

### `get_settings()`
- 위치: 줄 160
- 데코레이터: lru_cache
- 설명: 설정 싱글톤 반환

### `setup_logging(settings)`
- 위치: 줄 165
- 설명: 로깅 설정

프로덕션: JSON 포맷 (구조화된 로그)
개발: 텍스트 포맷 (가독성)
