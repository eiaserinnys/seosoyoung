# service/task_storage.py

> 경로: `seosoyoung/soul/service/task_storage.py`

## 개요

Task Storage - 태스크 영속화 관리

JSON 파일 기반의 태스크 상태 영속화를 담당합니다.

## 클래스

### `TaskStorage`
- 위치: 줄 23
- 설명: 태스크 영속화 관리자

JSON 파일을 통해 태스크 상태를 영속화합니다.
- debounce 저장으로 I/O 최적화
- atomic write로 데이터 무결성 보장

#### 메서드

- `__init__(self, storage_path)` (줄 32): Args:
- `async load(self, tasks)` (줄 40): 파일에서 태스크 로드
- `async _save(self, tasks)` (줄 88): 태스크를 파일에 저장 (내부용)
- `async save(self, tasks)` (줄 114): 태스크 상태 저장 (public interface)
- `async schedule_save(self, tasks)` (줄 118): 저장 예약 (debounce)

## 내부 의존성

- `seosoyoung.soul.service.task_models.Task`
- `seosoyoung.soul.service.task_models.TaskStatus`
- `seosoyoung.soul.service.task_models.datetime_to_str`
- `seosoyoung.soul.service.task_models.utc_now`
