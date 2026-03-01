# memory/observation_pipeline.py

> 경로: `seosoyoung/slackbot/plugins/memory/observation_pipeline.py`

## 개요

관찰 파이프라인

매턴마다 Observer를 호출하여 세션 관찰 로그를 갱신하고, 장기 기억 후보를 수집합니다.

흐름:
1. pending 버퍼 로드 → 이번 턴 메시지와 합산 → 최소 토큰 미만이면 pending에 누적 후 스킵
2. Observer 호출 (매턴) → 세션 관찰 로그 갱신 → pending 비우기
3. candidates가 있으면 장기 기억 후보 버퍼에 적재
4. 관찰 로그가 reflection 임계치를 넘으면 Reflector로 압축
5. 후보 버퍼 토큰 합산 → promotion 임계치 초과 시 Promoter 호출
6. 장기 기억 토큰 → compaction 임계치 초과 시 Compactor 호출

## 함수

### `_send_debug_log(channel, text, thread_ts)`
- 위치: 줄 33
- 설명: OM 디버그 로그를 슬랙 채널에 발송. 메시지 ts를 반환.

### `_update_debug_log(channel, ts, text)`
- 위치: 줄 50
- 설명: 기존 디버그 로그 메시지를 수정

### `_format_tokens(n)`
- 위치: 줄 64
- 설명: 토큰 수를 천 단위 콤마 포맷

### `_blockquote(text, max_chars)`
- 위치: 줄 69
- 설명: 텍스트를 슬랙 blockquote 형식으로 변환. 길면 잘라서 표시.

### `_extract_new_observations(existing, updated)`
- 위치: 줄 80
- 설명: 기존 관찰과 갱신된 관찰을 비교하여 새로 추가된 항목만 추출합니다.

ID 기반: 기존에 없는 ID를 가진 항목을 새 항목으로 간주합니다.

### `async observe_conversation(store, observer, thread_ts, user_id, messages, min_turn_tokens, reflector, reflection_threshold, promoter, promotion_threshold, compactor, compaction_threshold, compaction_target, debug_channel, anchor_ts)`
- 위치: 줄 100
- 설명: 매턴 Observer를 호출하여 세션 관찰 로그를 갱신하고 후보를 수집합니다.

Args:
    store: 관찰 로그 저장소
    observer: Observer 인스턴스
    thread_ts: 세션(스레드) 타임스탬프 — 저장 키
    user_id: 사용자 ID — 메타데이터용
    messages: 이번 턴 대화 내역
    min_turn_tokens: 최소 턴 토큰 (이하 스킵)
    reflector: Reflector 인스턴스 (None이면 압축 건너뜀)
    reflection_threshold: Reflector 트리거 토큰 임계치
    promoter: Promoter 인스턴스 (None이면 승격 건너뜀)
    promotion_threshold: 후보 버퍼 → Promoter 트리거 토큰 임계치
    compactor: Compactor 인스턴스 (None이면 컴팩션 건너뜀)
    compaction_threshold: 장기 기억 → Compactor 트리거 토큰 임계치
    compaction_target: 컴팩션 목표 토큰
    debug_channel: 디버그 로그를 발송할 슬랙 채널

Returns:
    True: 관찰 수행됨, False: 스킵 또는 실패

### `async _try_promote(store, promoter, promotion_threshold, compactor, compaction_threshold, compaction_target, debug_channel, token_counter, anchor_ts)`
- 위치: 줄 321
- 설명: 후보 버퍼 토큰이 임계치를 넘으면 Promoter를 호출하고, 필요 시 Compactor도 호출.

### `async _try_compact(store, compactor, compaction_target, persistent_tokens, debug_channel, anchor_ts)`
- 위치: 줄 436
- 설명: 장기 기억 토큰이 임계치를 넘으면 archive 후 Compactor를 호출.

## 내부 의존성

- `seosoyoung.slackbot.config.Config`
- `seosoyoung.slackbot.plugins.memory.context_builder.render_observation_items`
- `seosoyoung.slackbot.plugins.memory.context_builder.render_persistent_items`
- `seosoyoung.slackbot.plugins.memory.observer.Observer`
- `seosoyoung.slackbot.plugins.memory.promoter.Compactor`
- `seosoyoung.slackbot.plugins.memory.promoter.Promoter`
- `seosoyoung.slackbot.plugins.memory.reflector.Reflector`
- `seosoyoung.slackbot.plugins.memory.store.MemoryRecord`
- `seosoyoung.slackbot.plugins.memory.store.MemoryStore`
- `seosoyoung.slackbot.plugins.memory.token_counter.TokenCounter`
