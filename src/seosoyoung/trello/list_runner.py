"""ListRunner - 리스트 정주행 기능

트렐로 리스트의 카드를 순차적으로 처리하고,
각 단계 완료 후 검증 세션을 실행하여 품질을 확인합니다.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ListNotFoundError(Exception):
    """리스트를 찾을 수 없을 때 발생하는 예외"""
    pass


class EmptyListError(Exception):
    """리스트에 카드가 없을 때 발생하는 예외"""
    pass


class ValidationStatus(Enum):
    """검증 결과 상태"""
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class SessionStatus(Enum):
    """리스트 정주행 세션 상태"""
    PENDING = "pending"      # 대기 중 (시작 전)
    RUNNING = "running"      # 실행 중
    PAUSED = "paused"        # 일시 중단
    VERIFYING = "verifying"  # 검증 세션 실행 중
    COMPLETED = "completed"  # 완료
    FAILED = "failed"        # 실패


@dataclass
class CardExecutionResult:
    """카드 실행 결과"""
    success: bool
    card_id: str
    output: str = ""
    error: Optional[str] = None
    session_id: Optional[str] = None


@dataclass
class ValidationResult:
    """검증 결과"""
    status: ValidationStatus
    card_id: str
    output: str = ""
    session_id: Optional[str] = None


@dataclass
class CardRunResult:
    """카드 실행 및 검증 전체 결과"""
    card_id: str
    execution_success: bool
    validation_status: ValidationStatus
    execution_output: str = ""
    validation_output: str = ""
    error: Optional[str] = None


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

    def get_paused_sessions(self) -> list[ListRunSession]:
        """중단된 세션 목록 조회

        PAUSED 상태인 세션만 반환합니다.

        Returns:
            중단된 세션 목록
        """
        return [
            session for session in self.sessions.values()
            if session.status == SessionStatus.PAUSED
        ]

    def find_session_by_list_name(
        self,
        list_name: str,
    ) -> Optional[ListRunSession]:
        """리스트 이름으로 활성 세션 검색

        COMPLETED, FAILED가 아닌 세션 중 리스트 이름이 일치하는 세션을 반환합니다.

        Args:
            list_name: 검색할 리스트 이름

        Returns:
            세션 또는 None
        """
        excluded_statuses = {SessionStatus.COMPLETED, SessionStatus.FAILED}
        for session in self.sessions.values():
            if (session.list_name == list_name and
                session.status not in excluded_statuses):
                return session
        return None

    def pause_run(
        self,
        session_id: str,
        reason: str,
    ) -> bool:
        """정주행 세션 중단

        RUNNING 또는 VERIFYING 상태인 세션만 중단할 수 있습니다.

        Args:
            session_id: 세션 ID
            reason: 중단 사유

        Returns:
            중단 성공 여부
        """
        session = self.get_session(session_id)
        if not session:
            return False

        # RUNNING 또는 VERIFYING 상태에서만 중단 가능
        pausable_statuses = {SessionStatus.RUNNING, SessionStatus.VERIFYING}
        if session.status not in pausable_statuses:
            return False

        session.status = SessionStatus.PAUSED
        session.error_message = reason
        self.save_sessions()
        logger.info(f"세션 중단: {session_id} - {reason}")
        return True

    def resume_run(
        self,
        session_id: str,
    ) -> bool:
        """중단된 정주행 세션 재개

        PAUSED 또는 FAILED 상태인 세션만 재개할 수 있습니다.

        Args:
            session_id: 세션 ID

        Returns:
            재개 성공 여부
        """
        session = self.get_session(session_id)
        if not session:
            return False

        # PAUSED 또는 FAILED 상태에서만 재개 가능
        resumable_statuses = {SessionStatus.PAUSED, SessionStatus.FAILED}
        if session.status not in resumable_statuses:
            return False

        session.status = SessionStatus.RUNNING
        session.error_message = None
        self.save_sessions()
        logger.info(f"세션 재개: {session_id}")
        return True

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

    async def start_run_by_name(
        self,
        list_name: str,
        trello_client,
    ) -> ListRunSession:
        """리스트 이름으로 정주행 세션 시작

        Args:
            list_name: 트렐로 리스트 이름
            trello_client: 트렐로 클라이언트 (get_lists, get_cards_by_list 메서드 필요)

        Returns:
            생성된 세션

        Raises:
            ListNotFoundError: 리스트를 찾을 수 없는 경우
            EmptyListError: 리스트에 카드가 없는 경우
        """
        # 리스트 이름으로 ID 조회
        lists = await trello_client.get_lists()
        list_id = None
        for lst in lists:
            if lst.get("name") == list_name:
                list_id = lst.get("id")
                break

        if not list_id:
            raise ListNotFoundError(f"리스트를 찾을 수 없습니다: {list_name}")

        # 리스트의 카드 목록 조회
        cards = await trello_client.get_cards_by_list(list_id)
        if not cards:
            raise EmptyListError(f"리스트에 카드가 없습니다: {list_name}")

        # 카드 ID 목록 추출
        card_ids = [card.get("id") for card in cards]

        # 세션 생성
        session = self.create_session(
            list_id=list_id,
            list_name=list_name,
            card_ids=card_ids,
        )

        logger.info(f"리스트 정주행 시작: {list_name} ({len(card_ids)}개 카드)")
        return session

    @staticmethod
    def _parse_validation_result(output: str) -> ValidationStatus:
        """검증 결과 마커 파싱

        VALIDATION_RESULT: PASS 또는 VALIDATION_RESULT: FAIL 형식의
        마커를 찾아 검증 상태를 반환합니다.

        Args:
            output: Claude 응답 텍스트

        Returns:
            ValidationStatus (PASS, FAIL, UNKNOWN)
        """
        pattern = r"VALIDATION_RESULT:\s*(PASS|FAIL)"
        match = re.search(pattern, output, re.IGNORECASE)

        if not match:
            return ValidationStatus.UNKNOWN

        result = match.group(1).upper()
        if result == "PASS":
            return ValidationStatus.PASS
        elif result == "FAIL":
            return ValidationStatus.FAIL
        return ValidationStatus.UNKNOWN

    async def process_next_card(
        self,
        session_id: str,
        trello_client,
    ) -> Optional[dict]:
        """다음 처리할 카드 정보 조회

        Args:
            session_id: 세션 ID
            trello_client: 트렐로 클라이언트 (get_card 메서드 필요)

        Returns:
            카드 정보 딕셔너리 또는 None (모두 처리된 경우)
        """
        card_id = self.get_next_card_id(session_id)
        if not card_id:
            return None

        card_info = await trello_client.get_card(card_id)
        return card_info

    async def execute_card(
        self,
        session_id: str,
        card_info: dict,
        claude_runner,
    ) -> CardExecutionResult:
        """카드 실행

        Args:
            session_id: 세션 ID
            card_info: 카드 정보 딕셔너리
            claude_runner: Claude Code 실행기

        Returns:
            CardExecutionResult
        """
        card_id = card_info.get("id", "")
        card_name = card_info.get("name", "")
        card_desc = card_info.get("desc", "")

        # 카드 내용으로 프롬프트 구성
        prompt = f"""다음 트렐로 카드의 작업을 수행해주세요.

## 카드 제목
{card_name}

## 카드 설명
{card_desc}

작업을 완료하면 결과를 알려주세요.
"""

        logger.info(f"카드 실행 시작: {card_id} - {card_name}")

        result = await claude_runner.run(prompt)

        if result.success:
            logger.info(f"카드 실행 완료: {card_id}")
            return CardExecutionResult(
                success=True,
                card_id=card_id,
                output=result.output,
                session_id=result.session_id,
            )
        else:
            logger.error(f"카드 실행 실패: {card_id} - {result.error}")
            return CardExecutionResult(
                success=False,
                card_id=card_id,
                output=result.output,
                error=result.error,
                session_id=result.session_id,
            )

    async def validate_completion(
        self,
        session_id: str,
        card_info: dict,
        execution_output: str,
        claude_runner,
    ) -> ValidationResult:
        """카드 완료 검증

        Args:
            session_id: 세션 ID
            card_info: 카드 정보 딕셔너리
            execution_output: 카드 실행 결과
            claude_runner: Claude Code 실행기

        Returns:
            ValidationResult
        """
        card_id = card_info.get("id", "")
        card_name = card_info.get("name", "")
        card_desc = card_info.get("desc", "")

        # 검증 프롬프트 구성
        prompt = f"""다음 작업의 완료 여부를 검증해주세요.

## 원래 작업
**제목**: {card_name}
**설명**: {card_desc}

## 실행 결과
{execution_output}

## 검증 요청
위 작업이 올바르게 완료되었는지 검증하고,
결과를 다음 형식으로 알려주세요:

VALIDATION_RESULT: PASS (또는 FAIL)

검증 항목:
1. 요청된 작업이 수행되었는가?
2. 테스트가 통과하는가? (해당되는 경우)
3. 코드 품질이 적절한가? (해당되는 경우)
"""

        logger.info(f"카드 검증 시작: {card_id}")

        result = await claude_runner.run(prompt)

        if not result.success:
            logger.error(f"카드 검증 실행 실패: {card_id}")
            return ValidationResult(
                status=ValidationStatus.UNKNOWN,
                card_id=card_id,
                output=result.error or "",
                session_id=result.session_id,
            )

        status = self._parse_validation_result(result.output)
        logger.info(f"카드 검증 결과: {card_id} - {status.value}")

        return ValidationResult(
            status=status,
            card_id=card_id,
            output=result.output,
            session_id=result.session_id,
        )

    async def run_next_card(
        self,
        session_id: str,
        trello_client,
        claude_runner,
        auto_pause_on_fail: bool = False,
    ) -> Optional[CardRunResult]:
        """다음 카드 실행 및 검증

        카드를 실행하고 검증까지 완료하는 전체 플로우를 수행합니다.

        Args:
            session_id: 세션 ID
            trello_client: 트렐로 클라이언트
            claude_runner: Claude Code 실행기
            auto_pause_on_fail: 검증 실패 시 자동 중단 여부

        Returns:
            CardRunResult 또는 None (모든 카드 처리 완료 시)
        """
        # 다음 카드 조회
        card_info = await self.process_next_card(session_id, trello_client)
        if not card_info:
            logger.info(f"세션 {session_id}: 모든 카드 처리 완료")
            self.update_session_status(session_id, SessionStatus.COMPLETED)
            return None

        card_id = card_info.get("id", "")
        card_name = card_info.get("name", "")

        # 카드 실행
        exec_result = await self.execute_card(session_id, card_info, claude_runner)

        if not exec_result.success:
            # 실행 실패 시 실패로 표시하고 반환
            self.mark_card_processed(session_id, card_id, "failed")
            if auto_pause_on_fail:
                self.pause_run(session_id, f"실행 실패: {card_name}")
            return CardRunResult(
                card_id=card_id,
                execution_success=False,
                validation_status=ValidationStatus.UNKNOWN,
                execution_output=exec_result.output,
                error=exec_result.error,
            )

        # 검증 세션 상태로 변경
        self.update_session_status(session_id, SessionStatus.VERIFYING)

        # 검증 실행
        val_result = await self.validate_completion(
            session_id,
            card_info,
            exec_result.output,
            claude_runner,
        )

        # 카드 처리 완료 표시
        result_status = "passed" if val_result.status == ValidationStatus.PASS else "failed"
        self.mark_card_processed(session_id, card_id, result_status)

        # 검증 실패 시 자동 중단
        if auto_pause_on_fail and val_result.status == ValidationStatus.FAIL:
            self.pause_run(session_id, f"검증 실패: {card_name}")
        else:
            # 검증 완료 후 다시 실행 상태로
            self.update_session_status(session_id, SessionStatus.RUNNING)

        return CardRunResult(
            card_id=card_id,
            execution_success=True,
            validation_status=val_result.status,
            execution_output=exec_result.output,
            validation_output=val_result.output,
        )
