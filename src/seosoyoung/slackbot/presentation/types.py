"""프레젠테이션 컨텍스트 타입 정의

claude/ 모듈 밖에 위치하여 엔진 독립성을 유지합니다.
executor에 전달되는 opaque 객체로, 콜백과 ResultProcessor가 사용합니다.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PresentationContext:
    """프레젠테이션 레이어가 관리하는 실행 컨텍스트

    claude/ 밖에 위치하여 엔진 패키지의 Slack 의존성을 제거합니다.
    콜백 팩토리와 ResultProcessor가 이 객체의 필드를 읽고 갱신합니다.
    """

    channel: str
    thread_ts: str
    msg_ts: str
    say: Any          # SayFunction (duck-typed)
    client: Any       # SlackClient (duck-typed)
    effective_role: str = "admin"
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    # Slack 메시지 ts 추적 (mutable - 콜백이 갱신)
    last_msg_ts: Optional[str] = None
    main_msg_ts: Optional[str] = None
    # 트렐로
    trello_card: Any = None
    is_trello_mode: bool = False
    # 스레드 상태
    is_existing_thread: bool = False
    is_thread_reply: bool = False
    # OM (Observation Memory) 디버그 채널
    om_anchor_ts: Optional[str] = None
    # DM (트렐로 모드용)
    dm_channel_id: Optional[str] = None
    dm_thread_ts: Optional[str] = None
    dm_last_reply_ts: Optional[str] = None
    # 컴팩트 알림 메시지 ts (on_compact가 전송한 메시지, 완료 후 갱신용)
    compact_msg_ts: Optional[str] = None
    # stale 사고 과정 체크 타임스탬프 (monotonic, rate-limit용)
    _last_stale_check: float = 0.0
