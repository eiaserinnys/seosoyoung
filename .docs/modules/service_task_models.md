# service/task_models.py

> 경로: `seosoyoung/soul/service/task_models.py`

## 개요

Task Models - 태스크 관련 데이터 모델 및 예외

태스크의 핵심 데이터 구조를 정의합니다.

## 클래스

### `TaskStatus` (str, Enum)
- 위치: 줄 14
- 설명: 태스크 상태

### `TaskConflictError` (Exception)
- 위치: 줄 21
- 설명: 태스크 충돌 오류 (같은 키로 running 태스크 존재)

### `TaskNotFoundError` (Exception)
- 위치: 줄 26
- 설명: 태스크 없음 오류

### `TaskNotRunningError` (Exception)
- 위치: 줄 31
- 설명: 태스크가 running 상태가 아님

### `Task`
- 위치: 줄 52
- 설명: 태스크 데이터

#### 메서드

- `key(self)` (줄 79): 태스크 키
- `to_dict(self)` (줄 83): 영속화용 dict 변환
- `from_dict(cls, data)` (줄 100): dict에서 복원

## 함수

### `utc_now()`
- 위치: 줄 36
- 설명: 현재 UTC 시간 반환

### `datetime_to_str(dt)`
- 위치: 줄 41
- 설명: datetime을 ISO 문자열로 변환

### `str_to_datetime(s)`
- 위치: 줄 46
- 설명: ISO 문자열을 datetime으로 변환
