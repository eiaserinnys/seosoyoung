# claude/session_context.py

> 경로: `seosoyoung/slackbot/claude/session_context.py`

## 개요

세션 컨텍스트 주입

세션 생성 시 채널 대화 맥락을 구성합니다.
모니터링 채널이면 judged/pending 데이터를 병합하여 더 풍부한 컨텍스트를 제공합니다.

## 클래스

### `ChannelStoreProtocol` (Protocol)
- 위치: 줄 14
- 설명: ChannelStore가 구현해야 하는 인터페이스

#### 메서드

- `load_judged(self, channel_id)` (줄 17): 
- `load_pending(self, channel_id)` (줄 18): 

## 함수

### `build_initial_context(channel_id, slack_messages, monitored_channels, channel_store)`
- 위치: 줄 23
- 설명: 세션 최초 생성 시 채널 컨텍스트를 구성합니다.

Args:
    channel_id: 슬랙 채널 ID
    slack_messages: 슬랙 API로 가져온 최근 메시지 목록
    monitored_channels: 모니터링 대상 채널 ID 목록
    channel_store: ChannelStore 인스턴스 (모니터링 채널 아니면 None 가능)

Returns:
    {
        "messages": list[dict],  # 시간순 정렬된 메시지 (최대 7개)
        "last_seen_ts": str,     # 가장 마지막 메시지의 ts
        "source_type": str,      # "thread" | "hybrid"
    }

### `build_followup_context(channel_id, last_seen_ts, channel_store, monitored_channels)`
- 위치: 줄 75
- 설명: 후속 요청 시 last_seen_ts 이후 미전송 메시지를 구성합니다.

모니터링 채널이면 judged/pending에서 last_seen_ts 이후 메시지를 가져오고
linked 체인 정보도 포함합니다.

Args:
    channel_id: 슬랙 채널 ID
    last_seen_ts: 마지막으로 세션에 전달된 메시지의 ts
    channel_store: ChannelStore 인스턴스
    monitored_channels: 모니터링 대상 채널 ID 목록

Returns:
    {
        "messages": list[dict],  # 시간순 정렬된 미전송 메시지
        "last_seen_ts": str,     # 업데이트된 last_seen_ts
    }

### `format_hybrid_context(messages, source_type)`
- 위치: 줄 142
- 설명: hybrid 세션용 채널 컨텍스트를 프롬프트 텍스트로 포맷합니다.

Args:
    messages: 시간순 정렬된 메시지 목록
    source_type: "thread" | "channel" | "hybrid"

Returns:
    포맷된 컨텍스트 문자열

### `_merge_messages()`
- 위치: 줄 176
- 설명: 여러 메시지 소스를 ts 기준으로 중복 제거하며 병합합니다.

먼저 나오는 소스의 메시지가 우선합니다 (judged > pending > slack).
