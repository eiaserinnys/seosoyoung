"""Claude Code 세션 관리

스레드 ID ↔ 세션 ID 매핑을 관리합니다.
세션 락과 실행 상태 추적도 포함합니다.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime

from seosoyoung.slackbot.config import Config

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Claude Code 세션 정보"""
    thread_ts: str          # Slack 스레드 타임스탬프
    channel_id: str         # Slack 채널 ID
    user_id: str = ""       # 세션 생성자 Slack ID
    username: str = ""      # 세션 생성자 username
    role: str = "viewer"    # 역할: "admin" | "viewer"
    session_id: Optional[str] = None  # Claude Code 세션 ID
    created_at: str = ""    # 생성 시각
    updated_at: str = ""    # 마지막 업데이트 시각
    message_count: int = 0  # 메시지 수
    source_type: str = "thread"  # 세션 출처: "thread" | "channel" | "hybrid"
    last_seen_ts: str = ""  # 마지막으로 세션에 전달된 메시지의 ts

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
        self.session_dir = session_dir or Path(Config.get_session_path())
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

    def create(
        self,
        thread_ts: str,
        channel_id: str,
        user_id: str = "",
        username: str = "",
        role: str = "viewer",
        source_type: str = "thread",
        last_seen_ts: str = "",
    ) -> Session:
        """새 세션 생성"""
        session = Session(
            thread_ts=thread_ts,
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            role=role,
            source_type=source_type,
            last_seen_ts=last_seen_ts,
        )
        self._save(session)
        self._cache[thread_ts] = session
        logger.info(f"세션 생성: thread_ts={thread_ts}, user={username}, role={role}")
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

    def update_thread_ts(self, old_thread_ts: str, new_thread_ts: str) -> Optional[Session]:
        """세션의 thread_ts 변경 (멘션 응답 시 사용)

        채널 멘션 후 응답 메시지가 새 스레드 부모가 되어야 할 때 사용합니다.
        기존 파일을 삭제하고 새 thread_ts로 파일을 생성합니다.

        Args:
            old_thread_ts: 기존 thread_ts (멘션 메시지 ts)
            new_thread_ts: 새 thread_ts (응답 메시지 ts)

        Returns:
            업데이트된 Session 또는 None
        """
        session = self.get(old_thread_ts)
        if not session:
            return None

        # 기존 파일 삭제
        old_file = self._get_session_file(old_thread_ts)
        if old_file.exists():
            old_file.unlink()

        # 캐시에서도 제거
        self._cache.pop(old_thread_ts, None)

        # 새 thread_ts로 업데이트
        session.thread_ts = new_thread_ts
        session.updated_at = datetime.now().isoformat()

        # 새 파일로 저장 및 캐시
        self._save(session)
        self._cache[new_thread_ts] = session

        logger.info(f"세션 thread_ts 변경: {old_thread_ts} -> {new_thread_ts}")
        return session

    def update_last_seen_ts(self, thread_ts: str, last_seen_ts: str) -> Optional[Session]:
        """세션의 last_seen_ts 업데이트"""
        session = self.get(thread_ts)
        if session:
            session.last_seen_ts = last_seen_ts
            session.updated_at = datetime.now().isoformat()
            self._save(session)
            logger.debug(f"last_seen_ts 업데이트: thread_ts={thread_ts}, last_seen_ts={last_seen_ts}")
        return session

    def update_user(
        self,
        thread_ts: str,
        user_id: str = "",
        username: str = "",
        role: str = "",
    ) -> Optional[Session]:
        """세션의 사용자 정보 업데이트 (개입 세션 → 멘션 시 승격)"""
        session = self.get(thread_ts)
        if not session:
            return None
        if user_id:
            session.user_id = user_id
        if username:
            session.username = username
        if role:
            session.role = role
        session.updated_at = datetime.now().isoformat()
        self._save(session)
        logger.info(f"세션 사용자 업데이트: thread_ts={thread_ts}, user={username}, role={role}")
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

    def cleanup_old_sessions(self, threshold_hours: int = 24) -> int:
        """오래된 세션 정리

        Args:
            threshold_hours: 정리 기준 시간 (시간 단위, 기본 24시간)

        Returns:
            정리된 세션 수
        """
        cleaned = 0
        now = datetime.now()

        for file_path in self.session_dir.glob("session_*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                created_at = datetime.fromisoformat(data.get("created_at", ""))
                age_hours = (now - created_at).total_seconds() / 3600

                if age_hours >= threshold_hours:
                    thread_ts = data.get("thread_ts")
                    file_path.unlink()
                    if thread_ts and thread_ts in self._cache:
                        del self._cache[thread_ts]
                    cleaned += 1
                    logger.info(f"세션 정리: thread_ts={thread_ts}, age={age_hours:.1f}h")
            except Exception as e:
                logger.error(f"세션 정리 실패: {file_path}, {e}")

        return cleaned


class SessionRuntime:
    """세션 실행 상태 관리자

    세션 락(동시 실행 방지)과 실행 상태 추적을 담당합니다.
    """

    def __init__(self, on_session_stopped: Optional[Callable] = None):
        """
        Args:
            on_session_stopped: 개별 세션이 종료될 때마다 호출될 콜백
        """
        # 실행 중인 세션 락 (스레드별 동시 실행 방지)
        # RLock 사용: 같은 스레드에서 여러 번 acquire 가능 (재진입 가능)
        self._session_locks: dict[str, threading.RLock] = {}
        self._locks_lock = threading.Lock()

        # 현재 실행 중인 세션 추적 (락이 acquire된 thread_ts 집합)
        self._running_sessions: set[str] = set()
        self._running_sessions_lock = threading.Lock()

        # 세션 종료 시 콜백 (재시작 대기 확인용)
        self._on_session_stopped = on_session_stopped

    def get_session_lock(self, thread_ts: str) -> threading.RLock:
        """스레드별 락 반환 (없으면 생성)"""
        with self._locks_lock:
            if thread_ts not in self._session_locks:
                self._session_locks[thread_ts] = threading.RLock()
            return self._session_locks[thread_ts]

    def mark_session_running(self, thread_ts: str) -> None:
        """세션을 실행 중으로 표시"""
        with self._running_sessions_lock:
            self._running_sessions.add(thread_ts)
        logger.debug(f"세션 실행 시작: thread_ts={thread_ts}")

    def mark_session_stopped(self, thread_ts: str) -> None:
        """세션 실행 종료 표시

        세션 종료 후 대기 중인 재시작 요청이 있으면 확인합니다.
        """
        with self._running_sessions_lock:
            self._running_sessions.discard(thread_ts)
        logger.debug(f"세션 실행 종료: thread_ts={thread_ts}")

        # 콜백 호출 (재시작 대기 확인 등)
        if self._on_session_stopped is not None:
            self._on_session_stopped()

    def get_running_session_count(self) -> int:
        """현재 실행 중인 세션 수 반환"""
        with self._running_sessions_lock:
            return len(self._running_sessions)

    def set_on_session_stopped(self, callback: Callable) -> None:
        """세션 종료 콜백 설정 (초기화 후 설정 가능)"""
        self._on_session_stopped = callback
