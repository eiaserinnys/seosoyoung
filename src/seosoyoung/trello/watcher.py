"""Trello 워처 - To Go 리스트 감시 및 처리"""

import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from seosoyoung.config import Config
from seosoyoung.trello.client import TrelloClient, TrelloCard

logger = logging.getLogger(__name__)


@dataclass
class TrackedCard:
    """추적 중인 카드 정보 (To Go 리스트 감시용)"""
    card_id: str
    card_name: str
    card_url: str  # 카드 URL (슬랙 링크용)
    list_id: str
    list_key: str  # "to_go" (단일 모니터링 포인트)
    thread_ts: str
    channel_id: str
    detected_at: str
    session_id: Optional[str] = None  # Claude 세션 ID
    has_execute: bool = False  # Execute 레이블 유무


@dataclass
class ThreadCardInfo:
    """스레드 ↔ 카드 매핑 정보 (리액션 처리용)

    Claude 세션이 시작된 슬랙 스레드와 트렐로 카드의 연결을 유지합니다.
    TrackedCard와 달리 Claude 실행 완료 후에도 유지되어 리액션 기반 실행을 지원합니다.
    """
    thread_ts: str
    channel_id: str
    card_id: str
    card_name: str
    card_url: str
    session_id: Optional[str] = None
    has_execute: bool = False
    created_at: str = ""


class TrelloWatcher:
    """Trello 리스트 감시자

    To Go 리스트에 새 카드가 들어오면:
    1. 카드를 In Progress로 이동
    2. Slack에 알림 메시지 전송
    3. Claude Code 세션 시작
    4. Execute 레이블 유무에 따라:
       - 없음: 계획 수립 후 Backlog로 이동
       - 있음: 작업 실행 후 Review/Blocked로 이동
    """

    def __init__(
        self,
        slack_client,
        session_manager,
        claude_runner_factory: Callable,
        get_session_lock: Optional[Callable[[str], threading.Lock]] = None,
        notify_channel: Optional[str] = None,
        poll_interval: int = 60,  # 1분
        data_dir: Optional[Path] = None,
    ):
        """
        Args:
            slack_client: Slack WebClient
            session_manager: SessionManager 인스턴스
            claude_runner_factory: (session, prompt, msg_ts, channel, say, client) -> None
            get_session_lock: 스레드별 락 반환 함수 (thread_ts -> Lock)
            notify_channel: 알림 채널 ID
            poll_interval: 폴링 간격 (초)
            data_dir: 상태 파일 저장 디렉토리
        """
        self.slack_client = slack_client
        self.session_manager = session_manager
        self.claude_runner_factory = claude_runner_factory
        self.get_session_lock = get_session_lock
        self.notify_channel = notify_channel or Config.TRELLO_NOTIFY_CHANNEL
        self.poll_interval = poll_interval

        self.trello = TrelloClient()
        self.watch_lists = Config.TRELLO_WATCH_LISTS

        # 상태 저장 경로
        self.data_dir = data_dir or Path(Config.get_session_path()).parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tracked_file = self.data_dir / "tracked_cards.json"
        self.thread_cards_file = self.data_dir / "thread_cards.json"

        # 추적 중인 카드 (To Go 리스트 감시용 - Claude 실행 완료 시 삭제)
        self._tracked: dict[str, TrackedCard] = {}
        self._load_tracked()

        # 스레드 ↔ 카드 매핑 (리액션 처리용 - 영구 유지)
        self._thread_cards: dict[str, ThreadCardInfo] = {}  # thread_ts -> ThreadCardInfo
        self._load_thread_cards()

        # 워처 스레드
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._paused = False
        self._pause_lock = threading.Lock()

    def _load_tracked(self):
        """추적 상태 로드"""
        if self.tracked_file.exists():
            try:
                data = json.loads(self.tracked_file.read_text(encoding="utf-8"))
                for card_id, card_data in data.items():
                    # 하위 호환성: 새 필드가 없으면 기본값 사용
                    if "card_url" not in card_data:
                        card_data["card_url"] = ""
                    if "session_id" not in card_data:
                        card_data["session_id"] = None
                    if "has_execute" not in card_data:
                        card_data["has_execute"] = False
                    self._tracked[card_id] = TrackedCard(**card_data)
                logger.info(f"추적 상태 로드: {len(self._tracked)}개 카드")
            except Exception as e:
                logger.error(f"추적 상태 로드 실패: {e}")

    def _save_tracked(self):
        """추적 상태 저장"""
        try:
            data = {k: asdict(v) for k, v in self._tracked.items()}
            self.tracked_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"추적 상태 저장 실패: {e}")

    def _load_thread_cards(self):
        """스레드-카드 매핑 로드"""
        if self.thread_cards_file.exists():
            try:
                data = json.loads(self.thread_cards_file.read_text(encoding="utf-8"))
                for thread_ts, info_data in data.items():
                    self._thread_cards[thread_ts] = ThreadCardInfo(**info_data)
                logger.info(f"스레드-카드 매핑 로드: {len(self._thread_cards)}개")
            except Exception as e:
                logger.error(f"스레드-카드 매핑 로드 실패: {e}")

    def _save_thread_cards(self):
        """스레드-카드 매핑 저장"""
        try:
            data = {k: asdict(v) for k, v in self._thread_cards.items()}
            self.thread_cards_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"스레드-카드 매핑 저장 실패: {e}")

    def _register_thread_card(self, tracked: TrackedCard):
        """스레드-카드 매핑 등록"""
        info = ThreadCardInfo(
            thread_ts=tracked.thread_ts,
            channel_id=tracked.channel_id,
            card_id=tracked.card_id,
            card_name=tracked.card_name,
            card_url=tracked.card_url,
            session_id=tracked.session_id,
            has_execute=tracked.has_execute,
            created_at=tracked.detected_at,
        )
        self._thread_cards[tracked.thread_ts] = info
        self._save_thread_cards()
        logger.debug(f"스레드-카드 매핑 등록: {tracked.thread_ts} -> {tracked.card_name}")

    def _untrack_card(self, card_id: str):
        """To Go 추적에서 카드 제거 (Claude 실행 완료 시 호출)"""
        if card_id in self._tracked:
            tracked = self._tracked.pop(card_id)
            self._save_tracked()
            logger.info(f"카드 추적 해제: {tracked.card_name} (Claude 실행 완료)")

    def update_thread_card_session_id(self, thread_ts: str, session_id: str) -> bool:
        """ThreadCardInfo의 session_id 업데이트

        Args:
            thread_ts: 스레드 타임스탬프
            session_id: Claude 세션 ID

        Returns:
            업데이트 성공 여부
        """
        if thread_ts in self._thread_cards:
            self._thread_cards[thread_ts].session_id = session_id
            self._save_thread_cards()
            return True
        return False

    def get_tracked_by_thread_ts(self, thread_ts: str) -> Optional[ThreadCardInfo]:
        """thread_ts로 ThreadCardInfo 조회 (리액션 처리용)

        Args:
            thread_ts: 슬랙 메시지 타임스탬프

        Returns:
            해당 thread_ts를 가진 ThreadCardInfo 또는 None
        """
        return self._thread_cards.get(thread_ts)

    def update_tracked_session_id(self, card_id: str, session_id: str) -> bool:
        """TrackedCard의 session_id 업데이트

        Args:
            card_id: 카드 ID
            session_id: Claude 세션 ID

        Returns:
            업데이트 성공 여부
        """
        if card_id in self._tracked:
            self._tracked[card_id].session_id = session_id
            self._save_tracked()
            return True
        return False

    def start(self):
        """워처 시작 (백그라운드 스레드)"""
        if not self.trello.is_configured():
            logger.warning("Trello API가 설정되지 않아 워처를 시작하지 않습니다.")
            return

        if self._thread and self._thread.is_alive():
            logger.warning("워처가 이미 실행 중입니다.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Trello 워처 시작: {self.poll_interval}초 간격")

    def stop(self):
        """워처 중지"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("Trello 워처 중지")

    def pause(self):
        """워처 일시 중단 (재시작 대기용)"""
        with self._pause_lock:
            self._paused = True
            logger.info("Trello 워처 일시 중단")

    def resume(self):
        """워처 재개"""
        with self._pause_lock:
            self._paused = False
            logger.info("Trello 워처 재개")

    @property
    def is_paused(self) -> bool:
        """일시 중단 상태인지 확인"""
        with self._pause_lock:
            return self._paused

    def _run(self):
        """워처 메인 루프"""
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as e:
                logger.exception(f"워처 폴링 오류: {e}")

            # 대기 (중간에 stop 가능)
            self._stop_event.wait(timeout=self.poll_interval)

    def _poll(self):
        """리스트 폴링"""
        # 일시 중단 상태면 스킵
        if self.is_paused:
            logger.debug("Trello 워처 일시 중단 상태 - 폴링 스킵")
            return

        if Config.TRELLO_POLLING_DEBUG:
            logger.debug("Trello 폴링 시작")

        # 현재 감시 리스트의 모든 카드 조회
        current_cards: dict[str, tuple[TrelloCard, str]] = {}  # card_id -> (card, list_key)

        for list_key, list_id in self.watch_lists.items():
            cards = self.trello.get_cards_in_list(list_id)
            for card in cards:
                current_cards[card.id] = (card, list_key)

        # 1. 새 카드 감지
        for card_id, (card, list_key) in current_cards.items():
            if card_id not in self._tracked:
                logger.info(f"새 카드 감지: [{list_key}] {card.name}")
                self._handle_new_card(card, list_key)

        # NOTE: _tracked 삭제는 폴링에서 하지 않음
        # Claude 실행 완료 시 _untrack_card()로 삭제됨

        # 2. Review 리스트에서 dueComplete된 카드를 Done으로 이동
        self._check_review_list_for_completion()

        # 3. 🏃 Run List 레이블 감지
        self._check_run_list_labels()

    def _check_review_list_for_completion(self):
        """Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동"""
        review_list_id = Config.TRELLO_REVIEW_LIST_ID
        done_list_id = Config.TRELLO_DONE_LIST_ID

        if not review_list_id or not done_list_id:
            return

        cards = self.trello.get_cards_in_list(review_list_id)
        for card in cards:
            if card.due_complete:
                logger.info(f"dueComplete 카드 감지: {card.name} -> Done으로 이동")
                if self.trello.move_card(card.id, done_list_id):
                    logger.info(f"카드 이동 완료: {card.name}")
                    # Slack에 알림
                    try:
                        self.slack_client.chat_postMessage(
                            channel=self.notify_channel,
                            text=f"✅ <{card.url}|*{card.name}*>"
                        )
                    except Exception as e:
                        logger.error(f"완료 알림 전송 실패: {e}")
                else:
                    logger.error(f"카드 이동 실패: {card.name}")

    def _add_spinner_prefix(self, card: TrelloCard) -> bool:
        """카드 제목에 🌀 prefix 추가"""
        if card.name.startswith("🌀"):
            return True  # 이미 있음
        new_name = f"🌀 {card.name}"
        return self.trello.update_card_name(card.id, new_name)

    def _remove_spinner_prefix(self, card_id: str, card_name: str) -> bool:
        """카드 제목에서 🌀 prefix 제거"""
        if not card_name.startswith("🌀"):
            return True  # 없음
        new_name = card_name.lstrip("🌀").lstrip()
        return self.trello.update_card_name(card_id, new_name)

    def _has_execute_label(self, card: TrelloCard) -> bool:
        """카드에 Execute 레이블이 있는지 확인"""
        for label in card.labels:
            if label.get("name", "").lower() == "execute":
                return True
        return False

    def _has_run_list_label(self, card: TrelloCard) -> bool:
        """카드에 🏃 Run List 레이블이 있는지 확인"""
        for label in card.labels:
            if label.get("name", "") == "🏃 Run List":
                return True
        return False

    def _get_run_list_label_id(self, card: TrelloCard) -> Optional[str]:
        """카드에서 🏃 Run List 레이블 ID 반환"""
        for label in card.labels:
            if label.get("name", "") == "🏃 Run List":
                return label.get("id")
        return None

    def _build_header(self, card_name: str, card_url: str, session_id: str = "") -> str:
        """슬랙 메시지 헤더 생성

        진행 상태(계획/실행/완료)는 헤더가 아닌 슬랙 이모지 리액션으로 표시합니다.

        Args:
            card_name: 카드 이름
            card_url: 카드 URL
            session_id: 세션 ID (표시용)

        Returns:
            헤더 문자열
        """
        session_display = f" | #️⃣ {session_id[:8]}" if session_id else ""
        return f"*🎫 <{card_url}|{card_name}>{session_display}*"

    def _handle_new_card(self, card: TrelloCard, list_key: str):
        """새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행"""
        # 1. 카드를 In Progress로 이동
        in_progress_list_id = Config.TRELLO_IN_PROGRESS_LIST_ID
        if in_progress_list_id:
            if self.trello.move_card(card.id, in_progress_list_id):
                logger.info(f"카드 In Progress로 이동: {card.name}")
            else:
                logger.warning(f"카드 In Progress 이동 실패: {card.name}")

        # 2. Execute 레이블 확인
        has_execute = self._has_execute_label(card)

        # 3. 알림 메시지 전송 (새 포맷: 모드는 리액션으로 표시)
        header = self._build_header(card.name, card.url)
        # 헤더와 초기 텍스트 사이에 빈 줄 추가
        initial_text = f"{header}\n\n`소영이 생각합니다...`"

        try:
            msg_result = self.slack_client.chat_postMessage(
                channel=self.notify_channel,
                text=initial_text
            )
            thread_ts = msg_result["ts"]
            logger.info(f"알림 전송 완료: thread_ts={thread_ts}")

            # 메시지 전송 후 상태 이모지 리액션 추가
            reaction = "arrow_forward" if has_execute else "thought_balloon"  # ▶️ or 💭
            try:
                self.slack_client.reactions_add(
                    channel=self.notify_channel,
                    timestamp=thread_ts,
                    name=reaction
                )
            except Exception as e:
                logger.debug(f"초기 상태 리액션 추가 실패: {e}")
        except Exception as e:
            logger.error(f"알림 전송 실패: {e}")
            return

        # 4. 🌀 prefix 추가
        if self._add_spinner_prefix(card):
            logger.info(f"🌀 prefix 추가: {card.name}")
        else:
            logger.warning(f"🌀 prefix 추가 실패: {card.name}")

        # 5. 추적 등록
        tracked = TrackedCard(
            card_id=card.id,
            card_name=card.name,
            card_url=card.url,
            list_id=card.list_id,
            list_key=list_key,
            thread_ts=thread_ts,
            channel_id=self.notify_channel,
            detected_at=datetime.now().isoformat(),
            has_execute=has_execute,
        )
        self._tracked[card.id] = tracked
        self._save_tracked()

        # 5-1. 스레드-카드 매핑 등록 (리액션 처리용)
        self._register_thread_card(tracked)

        # 6. 세션 생성
        session = self.session_manager.create(
            thread_ts=thread_ts,
            channel_id=self.notify_channel,
            user_id="trello_watcher",
            username="trello_watcher",
            role="admin"  # 워처는 admin 권한으로 실행
        )

        # 7. 프롬프트 생성 (Execute 레이블 유무에 따라)
        prompt = self._build_to_go_prompt(card, has_execute)

        # 8. Claude 실행 (별도 스레드에서)
        card_id_for_cleanup = card.id
        card_name_with_spinner = f"🌀 {card.name}"

        def run_claude():
            lock = None
            if self.get_session_lock:
                lock = self.get_session_lock(thread_ts)
                lock.acquire()
                logger.debug(f"워처 락 획득: thread_ts={thread_ts}")
            try:
                def say(text, thread_ts=None):
                    self.slack_client.chat_postMessage(
                        channel=self.notify_channel,
                        thread_ts=thread_ts or tracked.thread_ts,
                        text=text
                    )

                self.claude_runner_factory(
                    session=session,
                    prompt=prompt,
                    msg_ts=thread_ts,
                    channel=self.notify_channel,
                    say=say,
                    client=self.slack_client,
                    trello_card=tracked  # TrackedCard 정보 전달
                )
            except Exception as e:
                logger.exception(f"Claude 실행 오류 (워처): {e}")
            finally:
                # Claude 실행 완료 후 🌀 제거
                if self._remove_spinner_prefix(card_id_for_cleanup, card_name_with_spinner):
                    logger.info(f"🌀 prefix 제거: {card.name}")
                else:
                    logger.warning(f"🌀 prefix 제거 실패: {card.name}")
                # To Go 추적에서 제거 (새 카드 감지용)
                self._untrack_card(card_id_for_cleanup)
                # 락 해제
                if lock:
                    lock.release()
                    logger.debug(f"워처 락 해제: thread_ts={thread_ts}")

        claude_thread = threading.Thread(target=run_claude, daemon=True)
        claude_thread.start()

    def _build_task_context_hint(self) -> str:
        """태스크 컨텍스트 힌트 생성"""
        return """
태스크는 여러가지 이유로 중단되거나 재개될 수 있습니다.
아래 체크리스트와 코멘트를 참고하세요.
"""

    def _build_list_ids_context(self) -> str:
        """자주 사용하는 리스트 ID 컨텍스트 생성"""
        return """
## 리스트 ID (MCP 검색 불필요)
- 📥 Draft: 696ddb607d7a2be9fef20614
- 📦 Backlog: 696ddb707a578b0021173f72
- 🚧 Blocked: 696ddb735d4b4b17cdc67a2e
- 👀 Review: 696ddb72e70fe807b0199746
"""

    def _format_checklists(self, checklists: list[dict]) -> str:
        """체크리스트를 프롬프트용 문자열로 포맷"""
        if not checklists:
            return "(체크리스트 없음)"

        lines = []
        for cl in checklists:
            lines.append(f"### {cl['name']}")
            for item in cl.get("items", []):
                mark = "x" if item["state"] == "complete" else " "
                lines.append(f"- [{mark}] {item['name']}")
        return "\n".join(lines)

    def _format_comments(self, comments: list[dict]) -> str:
        """코멘트를 프롬프트용 문자열로 포맷"""
        if not comments:
            return "(코멘트 없음)"

        lines = []
        for c in comments:
            # 날짜에서 시간 부분만 추출 (2026-01-27T05:10:41.387Z -> 01-27 05:10)
            date_str = c.get("date", "")[:16].replace("T", " ") if c.get("date") else ""
            author = c.get("author", "Unknown")
            text = c.get("text", "").strip()
            # 첫 3줄만 미리보기
            preview = "\n".join(text.split("\n")[:3])
            if len(text.split("\n")) > 3:
                preview += "\n..."
            lines.append(f"**[{date_str}] {author}**\n{preview}")
        return "\n\n".join(lines)

    def _build_card_context(self, card_id: str, desc: str = "") -> str:
        """카드의 체크리스트, 코멘트, 리스트 ID 컨텍스트를 조합"""
        # 체크리스트 조회
        checklists = self.trello.get_card_checklists(card_id)
        checklists_text = self._format_checklists(checklists)

        # 코멘트 조회
        comments = self.trello.get_card_comments(card_id)
        comments_text = self._format_comments(comments)

        # 리스트 ID 컨텍스트
        list_ids_text = self._build_list_ids_context()

        context = f"""
## 카드 본문
{desc if desc else "(본문 없음)"}

## 체크리스트
{checklists_text}

## 코멘트
{comments_text}
{list_ids_text}"""
        return context

    def _build_to_go_prompt(self, card: TrelloCard, has_execute: bool = False) -> str:
        """To Go 카드용 프롬프트 생성

        Args:
            card: Trello 카드
            has_execute: Execute 레이블 유무
                - True: 실행 모드 (계획 수립 후 바로 실행)
                - False: 계획 모드 (계획 수립만 하고 Backlog로 이동)
        """
        # 카드 컨텍스트 (체크리스트, 코멘트, 리스트 ID) 조회
        card_context = self._build_card_context(card.id, card.desc)

        if has_execute:
            # 실행 모드: 계획 수립 후 바로 실행
            prompt = f"""🚀 To Go 리스트에 들어온 '{card.name}' 태스크를 실행해주세요.

카드 ID: {card.id}
카드 URL: {card.url}
{self._build_task_context_hint()}
{card_context}"""
        else:
            # 계획 모드: 계획 수립만 하고 Backlog로 이동
            prompt = f"""📋 To Go 리스트에 들어온 '{card.name}' 태스크의 계획을 수립해주세요.

**Execute 레이블이 없으므로 계획 수립만 진행합니다.**

1. 카드를 분석하고 계획을 수립하세요
2. 체크리스트로 세부 단계를 기록하세요
3. 완료 후 카드를 📦 Backlog로 이동하세요
4. 사용자가 Execute 레이블을 붙이고 다시 🚀 To Go로 보내면 실행됩니다

카드 ID: {card.id}
카드 URL: {card.url}
{self._build_task_context_hint()}
{card_context}"""
        return prompt

    def build_reaction_execute_prompt(self, info: ThreadCardInfo) -> str:
        """리액션 기반 실행용 프롬프트 생성

        사용자가 계획 수립 완료 메시지에 실행 리액션을 달았을 때 사용합니다.
        Execute 레이블이 있는 To Go 카드와 동일한 프롬프트를 생성합니다.

        Args:
            info: ThreadCardInfo 정보

        Returns:
            실행 프롬프트 문자열
        """
        # 카드의 본문 조회
        card = self.trello.get_card(info.card_id)
        desc = card.desc if card else ""

        # 카드 컨텍스트 (체크리스트, 코멘트, 리스트 ID) 조회
        card_context = self._build_card_context(info.card_id, desc)

        prompt = f"""🚀 리액션으로 실행이 요청된 '{info.card_name}' 태스크를 실행해주세요.

이전에 계획 수립이 완료된 태스크입니다.
체크리스트와 코멘트를 확인하고 계획에 따라 작업을 수행하세요.

카드 ID: {info.card_id}
카드 URL: {info.card_url}
{self._build_task_context_hint()}
{card_context}"""
        return prompt

    def _check_run_list_labels(self):
        """🏃 Run List 레이블을 가진 카드 감지 및 리스트 정주행 시작

        모든 리스트의 첫 번째 카드에서 🏃 Run List 레이블을 확인합니다.
        레이블이 발견되면:
        1. 해당 리스트의 정주행을 시작
        2. 첫 카드에서 레이블 제거
        """
        lists = self.trello.get_lists()

        for lst in lists:
            list_id = lst["id"]
            list_name = lst["name"]

            # 리스트의 모든 카드 조회
            cards = self.trello.get_cards_in_list(list_id)
            if not cards:
                continue

            # 첫 번째 카드만 확인
            first_card = cards[0]
            if not self._has_run_list_label(first_card):
                continue

            # 🏃 Run List 레이블 발견!
            logger.info(f"🏃 Run List 레이블 감지: {list_name} - {first_card.name}")

            # 레이블 제거
            label_id = self._get_run_list_label_id(first_card)
            if label_id:
                if self.trello.remove_label_from_card(first_card.id, label_id):
                    logger.info(f"🏃 Run List 레이블 제거: {first_card.name}")
                else:
                    logger.warning(f"🏃 Run List 레이블 제거 실패: {first_card.name}")

            # 리스트 정주행 시작
            self._start_list_run(list_id, list_name, cards)

    def _start_list_run(
        self,
        list_id: str,
        list_name: str,
        cards: list[TrelloCard],
    ):
        """리스트 정주행 시작

        Args:
            list_id: 리스트 ID
            list_name: 리스트 이름
            cards: 리스트의 카드 목록
        """
        logger.info(f"리스트 정주행 시작: {list_name} ({len(cards)}개 카드)")

        # TODO: Phase 6에서 구현
        # - ListRunner와 연동하여 세션 생성
        # - 슬랙에 정주행 시작 알림
        # - 첫 번째 카드부터 순차 실행
