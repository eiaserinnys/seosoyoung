# service/resource_manager.py

> 경로: `seosoyoung/mcp/soul/service/resource_manager.py`

## 개요

ResourceManager - 동시 실행 제한 관리

Claude Code 동시 실행 수를 제한하고 리소스를 관리합니다.

## 클래스

### `ResourceManager`
- 위치: 줄 18
- 설명: 동시 실행 제한 관리자

역할:
1. 전역 동시 실행 제한 (Semaphore)
2. 시스템 메모리 모니터링
3. 리소스 획득/해제 컨텍스트 매니저 제공

#### 메서드

- `__init__(self, max_concurrent)` (줄 28): Args:
- `max_concurrent(self)` (줄 41): 최대 동시 세션 수
- `active_count(self)` (줄 46): 현재 활성 세션 수
- `available_slots(self)` (줄 51): 사용 가능한 슬롯 수
- `can_acquire(self)` (줄 55): 리소스 획득 가능 여부 (non-blocking check)
- `async acquire(self, timeout)` (줄 65): 리소스 획득 컨텍스트 매니저
- `try_acquire(self)` (줄 111): 리소스 획득 시도 (non-blocking, 동기 버전)
- `release(self)` (줄 123): 리소스 해제 (try_acquire와 쌍으로 사용)
- `get_system_memory(self)` (줄 131): 시스템 전체 메모리 사용량 반환
- `get_stats(self)` (줄 146): 리소스 통계 반환
