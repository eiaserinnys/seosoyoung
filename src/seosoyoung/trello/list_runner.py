"""ListRunner - 리스트 정주행 기능

트렐로 리스트의 카드를 순차적으로 처리하고,
각 단계 완료 후 검증 세션을 실행하여 품질을 확인합니다.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SessionStatus(Enum):
    """리스트 정주행 세션 상태"""
    PENDING = "pending"      # 대기 중 (시작 전)
    RUNNING = "running"      # 실행 중
    PAUSED = "paused"        # 일시 중단
    VERIFYING = "verifying"  # 검증 세션 실행 중
    COMPLETED = "completed"  # 완료
    FAILED = "failed"        # 실패


@dataclass
class ListRunSession:
    """리스트 정주행 세션 정보"""
    session_id: str
    list_id: str
    list_name: str
    card_ids: list[str]
    status: SessionStatus
    created_at: str
    current_index: int = 0
    verify_session_id: Optional[str] = None
    processed_cards: dict[str, str] = field(default_factory=dict)  # card_id -> result
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """딕셔너리로 변환 (저장용)"""
        return {
            "session_id": self.session_id,
            "list_id": self.list_id,
            "list_name": self.list_name,
            "card_ids": self.card_ids,
            "status": self.status.value,
            "created_at": self.created_at,
            "current_index": self.current_index,
            "verify_session_id": self.verify_session_id,
            "processed_cards": self.processed_cards,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ListRunSession":
        """딕셔너리에서 생성 (로드용)"""
        return cls(
            session_id=data["session_id"],
            list_id=data["list_id"],
            list_name=data["list_name"],
            card_ids=data["card_ids"],
            status=SessionStatus(data["status"]),
            created_at=data["created_at"],
            current_index=data.get("current_index", 0),
            verify_session_id=data.get("verify_session_id"),
            processed_cards=data.get("processed_cards", {}),
            error_message=data.get("error_message"),
        )


class ListRunner:
    """리스트 정주행 관리자

    트렐로 리스트의 카드를 순차적으로 처리합니다.

    주요 기능:
    - 세션 생성: 리스트의 카드 목록을 받아 정주행 세션 생성
    - 진행 추적: 현재 처리 중인 카드 인덱스 관리
    - 상태 관리: 세션 상태 (대기/실행/일시중단/검증/완료/실패)
    - 영속성: 세션 정보를 파일에 저장하여 재시작 시 복원
    """

    SESSIONS_FILENAME = "list_run_sessions.json"

    def __init__(self, data_dir: Optional[Path] = None):
        """
        Args:
            data_dir: 세션 데이터 저장 디렉토리
        """
        self.data_dir = data_dir or Path.cwd() / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sessions_file = self.data_dir / self.SESSIONS_FILENAME
        self.sessions: dict[str, ListRunSession] = {}

        self._load_sessions()

    def _load_sessions(self):
        """세션 목록 로드"""
        if not self.sessions_file.exists():
            return

        try:
            data = json.loads(self.sessions_file.read_text(encoding="utf-8"))
            for session_id, session_data in data.items():
                self.sessions[session_id] = ListRunSession.from_dict(session_data)
            logger.info(f"세션 로드 완료: {len(self.sessions)}개")
        except Exception as e:
            logger.error(f"세션 로드 실패: {e}")
            self.sessions = {}

    def save_sessions(self):
        """세션 목록 저장"""
        try:
            data = {
                session_id: session.to_dict()
                for session_id, session in self.sessions.items()
            }
            self.sessions_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.debug(f"세션 저장 완료: {len(self.sessions)}개")
        except Exception as e:
            logger.error(f"세션 저장 실패: {e}")

    def create_session(
        self,
        list_id: str,
        list_name: str,
        card_ids: list[str],
    ) -> ListRunSession:
        """새 정주행 세션 생성

        Args:
            list_id: 트렐로 리스트 ID
            list_name: 트렐로 리스트 이름
            card_ids: 처리할 카드 ID 목록 (순서대로)

        Returns:
            생성된 세션
        """
        session_id = str(uuid.uuid4())[:8]
        session = ListRunSession(
            session_id=session_id,
            list_id=list_id,
            list_name=list_name,
            card_ids=card_ids,
            status=SessionStatus.PENDING,
            created_at=datetime.now().isoformat(),
        )
        self.sessions[session_id] = session
        self.save_sessions()
        logger.info(f"세션 생성: {session_id} - {list_name} ({len(card_ids)}개 카드)")
        return session

    def get_session(self, session_id: str) -> Optional[ListRunSession]:
        """세션 조회

        Args:
            session_id: 세션 ID

        Returns:
            세션 또는 None
        """
        return self.sessions.get(session_id)

    def update_session_status(
        self,
        session_id: str,
        status: SessionStatus,
        error_message: Optional[str] = None,
    ) -> bool:
        """세션 상태 업데이트

        Args:
            session_id: 세션 ID
            status: 새 상태
            error_message: 에러 메시지 (FAILED 상태인 경우)

        Returns:
            업데이트 성공 여부
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.status = status
        if error_message:
            session.error_message = error_message
        self.save_sessions()
        logger.info(f"세션 상태 업데이트: {session_id} -> {status.value}")
        return True

    def get_active_sessions(self) -> list[ListRunSession]:
        """활성 세션 목록 조회

        RUNNING, PAUSED, VERIFYING 상태인 세션만 반환합니다.

        Returns:
            활성 세션 목록
        """
        active_statuses = {
            SessionStatus.RUNNING,
            SessionStatus.PAUSED,
            SessionStatus.VERIFYING,
        }
        return [
            session for session in self.sessions.values()
            if session.status in active_statuses
        ]

    def mark_card_processed(
        self,
        session_id: str,
        card_id: str,
        result: str,
    ) -> bool:
        """카드 처리 완료 표시

        Args:
            session_id: 세션 ID
            card_id: 처리 완료된 카드 ID
            result: 처리 결과 (예: "completed", "skipped", "failed")

        Returns:
            성공 여부
        """
        session = self.get_session(session_id)
        if not session:
            return False

        session.processed_cards[card_id] = result
        session.current_index += 1
        self.save_sessions()
        logger.debug(f"카드 처리 완료: {card_id} -> {result}")
        return True

    def get_next_card_id(self, session_id: str) -> Optional[str]:
        """다음 처리할 카드 ID 조회

        Args:
            session_id: 세션 ID

        Returns:
            다음 카드 ID 또는 None (모두 처리된 경우)
        """
        session = self.get_session(session_id)
        if not session:
            return None

        if session.current_index >= len(session.card_ids):
            return None

        return session.card_ids[session.current_index]
