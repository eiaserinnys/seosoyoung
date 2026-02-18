"""rescue-bot 세션 관리 (경량 in-memory 버전)

메인 봇의 SessionManager에서 파일 저장, 역할 관리 등을 제외한 경량 버전입니다.
스레드 ts → 세션 정보를 in-memory dict로 관리합니다.
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Session:
    """세션 정보"""
    thread_ts: str
    channel_id: str
    session_id: Optional[str] = None
    created_at: str = ""
    message_count: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class SessionManager:
    """경량 세션 매니저 (in-memory)"""

    def __init__(self):
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, thread_ts: str) -> Optional[Session]:
        """스레드 ID로 세션 조회"""
        with self._lock:
            return self._sessions.get(thread_ts)

    def create(self, thread_ts: str, channel_id: str) -> Session:
        """새 세션 생성"""
        session = Session(thread_ts=thread_ts, channel_id=channel_id)
        with self._lock:
            self._sessions[thread_ts] = session
        return session

    def get_or_create(self, thread_ts: str, channel_id: str) -> Session:
        """세션 조회, 없으면 생성"""
        session = self.get(thread_ts)
        if session:
            return session
        return self.create(thread_ts, channel_id)

    def update_session_id(self, thread_ts: str, session_id: str) -> Optional[Session]:
        """Claude Code 세션 ID 업데이트"""
        session = self.get(thread_ts)
        if session:
            session.session_id = session_id
        return session

    def increment_message_count(self, thread_ts: str) -> Optional[Session]:
        """메시지 카운트 증가"""
        session = self.get(thread_ts)
        if session:
            session.message_count += 1
        return session

    def count(self) -> int:
        """세션 수"""
        with self._lock:
            return len(self._sessions)
