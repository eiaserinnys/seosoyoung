"""Claude Code 세션 관리

스레드 ID ↔ 세션 ID 매핑을 관리합니다.
"""

import json
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from seosoyoung.config import Config

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Claude Code 세션 정보"""
    thread_ts: str          # Slack 스레드 타임스탬프
    channel_id: str         # Slack 채널 ID
    session_id: Optional[str] = None  # Claude Code 세션 ID
    created_at: str = ""    # 생성 시각
    updated_at: str = ""    # 마지막 업데이트 시각
    message_count: int = 0  # 메시지 수

    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class SessionManager:
    """세션 매니저

    스레드 ID를 키로 세션 정보를 관리합니다.
    세션 정보는 sessions/ 폴더에 JSON 파일로 저장됩니다.
    """

    def __init__(self, session_dir: Optional[Path] = None):
        self.session_dir = session_dir or Path(Config.SESSION_PATH)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _get_session_file(self, thread_ts: str) -> Path:
        """세션 파일 경로 반환"""
        # thread_ts는 "1234567890.123456" 형식
        safe_name = thread_ts.replace(".", "_")
        return self.session_dir / f"session_{safe_name}.json"

    def get(self, thread_ts: str) -> Optional[Session]:
        """스레드 ID로 세션 조회"""
        # 캐시 확인
        if thread_ts in self._cache:
            return self._cache[thread_ts]

        # 파일에서 로드
        file_path = self._get_session_file(thread_ts)
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                session = Session(**data)
                self._cache[thread_ts] = session
                return session
            except Exception as e:
                logger.error(f"세션 로드 실패: {file_path}, {e}")

        return None

    def create(self, thread_ts: str, channel_id: str) -> Session:
        """새 세션 생성"""
        session = Session(thread_ts=thread_ts, channel_id=channel_id)
        self._save(session)
        self._cache[thread_ts] = session
        logger.info(f"세션 생성: thread_ts={thread_ts}")
        return session

    def update_session_id(self, thread_ts: str, session_id: str) -> Optional[Session]:
        """Claude Code 세션 ID 업데이트"""
        session = self.get(thread_ts)
        if session:
            session.session_id = session_id
            session.updated_at = datetime.now().isoformat()
            self._save(session)
            logger.info(f"세션 ID 업데이트: thread_ts={thread_ts}, session_id={session_id}")
        return session

    def increment_message_count(self, thread_ts: str) -> Optional[Session]:
        """메시지 카운트 증가"""
        session = self.get(thread_ts)
        if session:
            session.message_count += 1
            session.updated_at = datetime.now().isoformat()
            self._save(session)
        return session

    def _save(self, session: Session) -> None:
        """세션을 파일에 저장"""
        file_path = self._get_session_file(session.thread_ts)
        try:
            file_path.write_text(
                json.dumps(asdict(session), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"세션 저장 실패: {file_path}, {e}")

    def exists(self, thread_ts: str) -> bool:
        """세션 존재 여부 확인"""
        return self.get(thread_ts) is not None

    def list_active(self) -> list[Session]:
        """모든 활성 세션 목록"""
        sessions = []
        for file_path in self.session_dir.glob("session_*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                sessions.append(Session(**data))
            except Exception as e:
                logger.error(f"세션 로드 실패: {file_path}, {e}")
        return sessions

    def count(self) -> int:
        """활성 세션 수"""
        return len(list(self.session_dir.glob("session_*.json")))
