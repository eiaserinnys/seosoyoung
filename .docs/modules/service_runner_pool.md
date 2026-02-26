# service/runner_pool.py

> 경로: `seosoyoung/soul/service/runner_pool.py`

## 개요

ClaudeRunner 풀링 시스템

매 요청마다 발생하는 콜드 스타트를 제거하기 위해 ClaudeRunner 인스턴스를 풀링합니다.

## 풀 구조
- session pool: OrderedDict[session_id, (ClaudeRunner, last_used)] — LRU 캐시
- generic pool: deque[(ClaudeRunner, idle_since)] — pre-warm 클라이언트 큐

## 크기 제한
max_size는 idle pool (session + generic) 합산 크기를 제한합니다.

## 클래스

### `ClaudeRunnerPool`
- 위치: 줄 27
- 설명: ClaudeRunner 인스턴스 LRU 풀

LRU 기반 세션 풀과 제네릭 풀을 함께 관리합니다.
session_id가 있으면 같은 Claude 세션을 재사용하고,
없으면 pre-warm된 generic runner를 재사용합니다.

#### 메서드

- `__init__(self, max_size, idle_ttl, workspace_dir, allowed_tools, disallowed_tools, mcp_config_path, min_generic, maintenance_interval)` (줄 35): 
- `_total_size(self)` (줄 76): 현재 idle pool 총 크기
- `_make_runner(self)` (줄 80): 새 ClaudeRunner 인스턴스 생성 (pooled=True)
- `async _discard(self, runner, reason)` (줄 91): runner를 안전하게 폐기
- `async _evict_lru_unlocked(self)` (줄 98): LRU runner를 퇴거 (락 없이 — 이미 락을 보유한 상태에서 호출)
- `async acquire(self, session_id)` (줄 125): 풀에서 runner 획득
- `async release(self, runner, session_id)` (줄 186): 실행 완료 후 runner 반환
- `async evict_lru(self)` (줄 222): 가장 오래 사용되지 않은 runner를 disconnect & 제거 (공개 API)
- `async pre_warm(self, count)` (줄 227): N개의 generic runner를 미리 생성하여 generic pool에 추가
- `async _run_maintenance(self)` (줄 262): 유지보수 작업 1회 실행
- `async _maintenance_loop(self)` (줄 332): 백그라운드 유지보수 루프
- `async start_maintenance(self)` (줄 353): 유지보수 루프 백그라운드 태스크 시작
- `async shutdown(self)` (줄 364): 모든 runner disconnect 및 유지보수 루프 취소
- `stats(self)` (줄 401): 현재 풀 상태 반환

## 내부 의존성

- `seosoyoung.slackbot.claude.agent_runner.ClaudeRunner`
