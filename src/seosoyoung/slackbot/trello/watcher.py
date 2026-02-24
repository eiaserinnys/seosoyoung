"""Trello 워처 - To Go 리스트 감시 및 처리"""

import concurrent.futures
import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from seosoyoung.slackbot.config import Config
from seosoyoung.slackbot.trello.client import TrelloClient, TrelloCard
from seosoyoung.slackbot.trello.prompt_builder import PromptBuilder

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
    dm_thread_ts: Optional[str] = None  # DM 스레드 앵커 ts (인터벤션 매핑용)


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
        list_runner_ref: Optional[Callable] = None,
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
            list_runner_ref: ListRunner 인스턴스 참조 함수 (() -> ListRunner)
        """
        self.slack_client = slack_client
        self.session_manager = session_manager
        self.claude_runner_factory = claude_runner_factory
        self.get_session_lock = get_session_lock
        self.notify_channel = notify_channel or Config.trello.notify_channel
        self.poll_interval = poll_interval
        self.list_runner_ref = list_runner_ref

        self.trello = TrelloClient()
        self.prompt_builder = PromptBuilder(self.trello)
        self.watch_lists = Config.trello.watch_lists

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
                    if "dm_thread_ts" not in card_data:
                        card_data["dm_thread_ts"] = None
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

        if Config.trello.polling_debug:
            logger.debug("Trello 폴링 시작")

        # 현재 감시 리스트의 모든 카드 조회
        current_cards: dict[str, tuple[TrelloCard, str]] = {}  # card_id -> (card, list_key)

        for list_key, list_id in self.watch_lists.items():
            cards = self.trello.get_cards_in_list(list_id)
            for card in cards:
                current_cards[card.id] = (card, list_key)

        # 1. stale tracked 카드 정리 + 새 카드 감지
        self._cleanup_stale_tracked(current_cards)

        for card_id, (card, list_key) in current_cards.items():
            if card_id not in self._tracked:
                logger.info(f"새 카드 감지: [{list_key}] {card.name}")
                self._handle_new_card(card, list_key)

        # 2. Review 리스트에서 dueComplete된 카드를 Done으로 이동
        self._check_review_list_for_completion()

        # 3. 🏃 Run List 레이블 감지
        self._check_run_list_labels()

    # 만료 시간: 2시간
    STALE_THRESHOLD = timedelta(hours=2)

    def _cleanup_stale_tracked(self, current_cards: dict[str, tuple]):
        """만료된 _tracked 항목 정리 (방안 A + C)

        detected_at이 STALE_THRESHOLD 이상 경과한 카드 중:
        - 현재 감시 리스트에 있으면: untrack 후 _handle_new_card로 재처리 (방안 C)
        - 현재 감시 리스트에 없으면: 단순 untrack (방안 A)
        """
        now = datetime.now()
        stale_ids = []

        for card_id, tracked in self._tracked.items():
            try:
                detected = datetime.fromisoformat(tracked.detected_at)
            except (ValueError, TypeError):
                detected = now  # 파싱 실패 시 만료 안 시킴
            if now - detected >= self.STALE_THRESHOLD:
                stale_ids.append(card_id)

        for card_id in stale_ids:
            in_watch_list = card_id in current_cards
            tracked = self._tracked[card_id]
            logger.info(
                f"stale 카드 정리: {tracked.card_name} "
                f"(감시 리스트 {'내' if in_watch_list else '외'}, "
                f"경과: {now - datetime.fromisoformat(tracked.detected_at)})"
            )
            self._untrack_card(card_id)
            # 방안 C: 감시 리스트에 다시 있으면 _handle_new_card가 다음 루프에서 처리

    def _check_review_list_for_completion(self):
        """Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동"""
        review_list_id = Config.trello.review_list_id
        done_list_id = Config.trello.done_list_id

        if not review_list_id or not done_list_id:
            return

        cards = self.trello.get_cards_in_list(review_list_id)
        for card in cards:
            if card.due_complete:
                logger.info(f"dueComplete 카드 감지: {card.name} -> Done으로 이동")
                if self.trello.move_card(card.id, done_list_id):
                    logger.info(f"카드 이동 완료: {card.name}")
                    # Slack에 알림 (DM 대상이 있으면 DM으로, 없으면 notify_channel로)
                    try:
                        channel = self._get_dm_or_notify_channel()
                        self.slack_client.chat_postMessage(
                            channel=channel,
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

    def _get_dm_or_notify_channel(self) -> str:
        """DM 대상 사용자가 설정되어 있으면 DM 채널 ID를, 없으면 notify_channel을 반환

        Returns:
            채널 ID (DM 또는 notify_channel)
        """
        dm_target_user = Config.trello.dm_target_user_id
        if dm_target_user:
            try:
                dm_result = self.slack_client.conversations_open(users=dm_target_user)
                return dm_result["channel"]["id"]
            except Exception as e:
                logger.warning(f"DM 채널 열기 실패 (notify_channel로 폴백): {e}")
        return self.notify_channel

    def _open_dm_thread(self, card_name: str, card_url: str) -> tuple[Optional[str], Optional[str]]:
        """DM 채널을 열고 앵커 메시지를 전송하여 DM 스레드를 생성

        Args:
            card_name: 카드 이름 (앵커 메시지 헤더용)
            card_url: 카드 URL

        Returns:
            (dm_channel_id, dm_thread_ts) - DM 채널 ID와 앵커 메시지 ts
            실패 시 (None, None)
        """
        dm_target_user = Config.trello.dm_target_user_id
        if not dm_target_user:
            return None, None

        try:
            # DM 채널 열기
            dm_result = self.slack_client.conversations_open(users=dm_target_user)
            dm_channel_id = dm_result["channel"]["id"]

            # 앵커 메시지 전송
            anchor_text = f"🎫 *<{card_url}|{card_name}>*\n`사고 과정을 기록합니다...`"
            anchor_msg = self.slack_client.chat_postMessage(
                channel=dm_channel_id,
                text=anchor_text,
                blocks=[{
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": anchor_text}
                }]
            )
            dm_thread_ts = anchor_msg["ts"]
            logger.info(f"DM 스레드 생성: channel={dm_channel_id}, thread_ts={dm_thread_ts}")
            return dm_channel_id, dm_thread_ts
        except Exception as e:
            logger.warning(f"DM 스레드 생성 실패 (기존 동작으로 폴백): {e}")
            return None, None

    def _handle_new_card(self, card: TrelloCard, list_key: str):
        """새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행"""
        # 1. 카드를 In Progress로 이동
        in_progress_list_id = Config.trello.in_progress_list_id
        if in_progress_list_id:
            if self.trello.move_card(card.id, in_progress_list_id):
                logger.info(f"카드 In Progress로 이동: {card.name}")
            else:
                logger.warning(f"카드 In Progress 이동 실패: {card.name}")

        # 2. Execute 레이블 확인
        has_execute = self._has_execute_label(card)

        # 3. DM 스레드 생성 (사고 과정 출력용)
        dm_channel_id, dm_thread_ts = self._open_dm_thread(card.name, card.url)

        # 4. 메시지 채널 결정: DM이 있으면 DM을 메인으로, 없으면 notify_channel로 폴백
        if dm_channel_id and dm_thread_ts:
            # DM 모드: notify_channel에 메시지를 보내지 않음
            # DM 앵커 메시지가 이미 생성되어 있으므로 그것을 thread_ts로 사용
            thread_ts = dm_thread_ts
            msg_channel = dm_channel_id
            logger.info(f"DM 모드: channel={dm_channel_id}, thread_ts={dm_thread_ts}")
        else:
            # 폴백: notify_channel에 메시지 전송
            header = self._build_header(card.name, card.url)
            initial_text = f"{header}\n\n`소영이 생각합니다...`"

            try:
                msg_result = self.slack_client.chat_postMessage(
                    channel=self.notify_channel,
                    text=initial_text
                )
                thread_ts = msg_result["ts"]
                msg_channel = self.notify_channel
                logger.info(f"알림 전송 완료 (폴백): thread_ts={thread_ts}")

                # 상태 이모지 리액션 추가
                reaction = "arrow_forward" if has_execute else "thought_balloon"
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

        # 5. 🌀 prefix 추가
        if self._add_spinner_prefix(card):
            logger.info(f"🌀 prefix 추가: {card.name}")
        else:
            logger.warning(f"🌀 prefix 추가 실패: {card.name}")

        # 6. 추적 등록
        tracked = TrackedCard(
            card_id=card.id,
            card_name=card.name,
            card_url=card.url,
            list_id=card.list_id,
            list_key=list_key,
            thread_ts=thread_ts,
            channel_id=msg_channel,
            detected_at=datetime.now().isoformat(),
            has_execute=has_execute,
        )
        tracked.dm_thread_ts = dm_thread_ts  # DM 스레드 ts 저장
        self._tracked[card.id] = tracked
        self._save_tracked()

        # 6-1. 스레드-카드 매핑 등록 (리액션 처리용)
        self._register_thread_card(tracked)

        # 7. 세션 생성
        session = self.session_manager.create(
            thread_ts=thread_ts,
            channel_id=msg_channel,
            user_id="trello_watcher",
            username="trello_watcher",
            role="admin"  # 워처는 admin 권한으로 실행
        )

        # 8. 프롬프트 생성 (Execute 레이블 유무에 따라)
        prompt = self.prompt_builder.build_to_go(card, has_execute)

        # 9. Claude 실행 (별도 스레드에서)
        card_id_for_cleanup = card.id
        card_name_with_spinner = f"🌀 {card.name}"

        def on_finally():
            if self._remove_spinner_prefix(card_id_for_cleanup, card_name_with_spinner):
                logger.info(f"🌀 prefix 제거: {card.name}")
            else:
                logger.warning(f"🌀 prefix 제거 실패: {card.name}")
            self._untrack_card(card_id_for_cleanup)

        self._spawn_claude_thread(
            session=session,
            prompt=prompt,
            thread_ts=thread_ts,
            channel=msg_channel,
            tracked=tracked,
            dm_channel_id=dm_channel_id,
            dm_thread_ts=dm_thread_ts,
            on_finally=on_finally,
        )

    def build_reaction_execute_prompt(self, info: ThreadCardInfo) -> str:
        """하위 호환: PromptBuilder에 위임"""
        return self.prompt_builder.build_reaction_execute(info)

    def _build_to_go_prompt(self, card: TrelloCard, has_execute: bool = False) -> str:
        """하위 호환: PromptBuilder에 위임"""
        return self.prompt_builder.build_to_go(card, has_execute)

    def _spawn_claude_thread(
        self,
        *,
        session,
        prompt: str,
        thread_ts: str,
        channel: str,
        tracked: TrackedCard,
        dm_channel_id: Optional[str] = None,
        dm_thread_ts: Optional[str] = None,
        on_success: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        on_finally: Optional[Callable] = None,
    ):
        """Claude 실행 스레드 스포닝 (공통)

        _handle_new_card와 _process_list_run_card의 공통 패턴을 통합합니다.
        - 세션 락 획득/해제
        - say 클로저 생성
        - claude_runner_factory 호출
        - 성공/에러/최종 콜백 실행

        Args:
            session: Claude 세션
            prompt: 프롬프트
            thread_ts: 슬랙 스레드 타임스탬프
            channel: 슬랙 채널 ID
            tracked: TrackedCard 정보
            dm_channel_id: DM 채널 ID
            dm_thread_ts: DM 스레드 타임스탬프
            on_success: 성공 시 호출될 콜백
            on_error: 에러 시 호출될 콜백 (Exception을 인자로 받음)
            on_finally: 항상 호출될 콜백 (락 해제 전)
        """
        def run_claude():
            lock = None
            if self.get_session_lock:
                lock = self.get_session_lock(thread_ts)
                lock.acquire()
                logger.debug(f"워처 락 획득: thread_ts={thread_ts}")

            claude_succeeded = False
            try:
                def say(text, thread_ts=None, **kwargs):
                    self.slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts or tracked.thread_ts,
                        text=text
                    )

                self.claude_runner_factory(
                    session=session,
                    prompt=prompt,
                    msg_ts=thread_ts,
                    channel=channel,
                    say=say,
                    client=self.slack_client,
                    trello_card=tracked,
                    dm_channel_id=dm_channel_id,
                    dm_thread_ts=dm_thread_ts,
                )
                claude_succeeded = True
            except Exception as e:
                logger.exception(f"Claude 실행 오류 (워처): {e}")
                if on_error:
                    on_error(e)

            # on_success는 Claude 실행과 분리하여 호출
            # on_success 내부 예외가 on_error를 트리거하지 않도록 격리
            if claude_succeeded and on_success:
                try:
                    on_success()
                except Exception as e:
                    logger.exception(
                        f"on_success 콜백 오류 (체인 중단 가능): {e}"
                    )

            if on_finally:
                try:
                    on_finally()
                except Exception as e:
                    logger.exception(f"on_finally 콜백 오류: {e}")
            if lock:
                lock.release()
                logger.debug(f"워처 락 해제: thread_ts={thread_ts}")

        claude_thread = threading.Thread(target=run_claude, daemon=True)
        claude_thread.start()

    def _get_operational_list_ids(self) -> set[str]:
        """운영 리스트 ID 집합 반환 (정주행 대상에서 제외할 리스트)"""
        ids = set()
        # watch_lists (To Go 등)
        for list_id in self.watch_lists.values():
            if list_id:
                ids.add(list_id)
        # 기타 운영 리스트
        for list_id in (
            Config.trello.in_progress_list_id,
            Config.trello.review_list_id,
            Config.trello.done_list_id,
            Config.trello.backlog_list_id,
            Config.trello.blocked_list_id,
            Config.trello.draft_list_id,
        ):
            if list_id:
                ids.add(list_id)
        return ids

    def _check_run_list_labels(self):
        """🏃 Run List 레이블을 가진 카드 감지 및 리스트 정주행 시작

        운영 리스트(To Go, In Progress, Review, Done 등)를 제외한
        리스트의 첫 번째 카드에서 🏃 Run List 레이블을 확인합니다.
        레이블이 발견되면:
        1. 첫 카드에서 레이블 제거 (실패 시 정주행 시작 안 함)
        2. 해당 리스트의 정주행을 시작
        """
        lists = self.trello.get_lists()
        operational_ids = self._get_operational_list_ids()

        for lst in lists:
            list_id = lst["id"]
            list_name = lst["name"]

            # 운영 리스트는 정주행 대상에서 제외
            if list_id in operational_ids:
                continue

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

            # 레이블 제거 (실패 시 정주행 시작하지 않음)
            label_id = self._get_run_list_label_id(first_card)
            if label_id:
                if self.trello.remove_label_from_card(first_card.id, label_id):
                    logger.info(f"🏃 Run List 레이블 제거: {first_card.name}")
                else:
                    logger.warning(
                        f"🏃 Run List 레이블 제거 실패, 정주행 스킵: {first_card.name} "
                        f"(다음 폴링에서 재시도)"
                    )
                    continue
            else:
                logger.warning(f"🏃 Run List 레이블 ID를 찾을 수 없음: {first_card.name}")
                continue

            # 활성 정주행 세션 가드: 동일 리스트에 이미 활성 세션이 있으면 스킵
            list_runner = self.list_runner_ref() if self.list_runner_ref else None
            if list_runner:
                active_sessions = list_runner.get_active_sessions()
                already_running = any(
                    s.list_id == list_id for s in active_sessions
                )
                if already_running:
                    logger.warning(
                        f"이미 활성 정주행 세션이 있어 스킵: {list_name}"
                    )
                    continue

            # 리스트 정주행 시작
            self._start_list_run(list_id, list_name, cards)

    # 선제적 컴팩트 타임아웃 (초)
    COMPACT_TIMEOUT_SECONDS = 60

    def _preemptive_compact(self, thread_ts: str, channel: str, card_name: str):
        """카드 완료 후 선제적 컨텍스트 컴팩트

        정주행에서 카드 하나의 처리가 끝난 뒤 다음 카드로 넘어가기 전에
        세션 컨텍스트를 압축하여 자동 압축으로 인한 흐름 끊김을 방지합니다.

        타임아웃을 적용하여 compact_session이 무기한 block되는 것을 방지합니다.

        Args:
            thread_ts: 슬랙 스레드 타임스탬프 (세션 조회 키)
            channel: 슬랙 채널 ID (알림용)
            card_name: 카드 이름 (로그용)
        """
        session = self.session_manager.get(thread_ts)
        if not session or not session.session_id:
            logger.warning(f"선제적 컴팩트 스킵: 세션 또는 세션 ID 없음 (card={card_name})")
            return

        try:
            from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner
            runner = ClaudeRunner()

            # 타임아웃 적용: compact가 무기한 block되는 것을 방지
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    runner.run_sync, runner.compact_session(session.session_id)
                )
                try:
                    result = future.result(timeout=self.COMPACT_TIMEOUT_SECONDS)
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        f"선제적 컴팩트 타임아웃 ({self.COMPACT_TIMEOUT_SECONDS}s, 계속 진행): "
                        f"card={card_name}, session={session.session_id}"
                    )
                    return

            if result.success:
                logger.info(f"선제적 컴팩트 완료: card={card_name}, session={session.session_id}")
                # 컴팩트 후 새 세션 ID가 반환되면 업데이트
                if result.session_id and result.session_id != session.session_id:
                    self.session_manager.update_session_id(thread_ts, result.session_id)
                    logger.info(f"컴팩트 후 세션 ID 변경: {session.session_id} -> {result.session_id}")
            else:
                logger.warning(f"선제적 컴팩트 실패 (계속 진행): card={card_name}, error={result.error}")
        except Exception as e:
            logger.warning(f"선제적 컴팩트 예외 (계속 진행): card={card_name}, {e}")

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

        # ListRunner 참조 확인
        list_runner = self.list_runner_ref() if self.list_runner_ref else None
        if not list_runner:
            logger.warning("ListRunner가 설정되지 않아 정주행을 시작할 수 없습니다.")
            return

        # 카드 ID 목록 추출
        card_ids = [card.id for card in cards]

        # 세션 생성
        session = list_runner.create_session(
            list_id=list_id,
            list_name=list_name,
            card_ids=card_ids,
        )

        # DM 스레드 생성 (정주행 전용)
        dm_channel_id, dm_thread_ts = self._open_dm_thread(
            f"📋 {list_name} 정주행", ""
        )

        # 메시지 채널 결정
        if dm_channel_id and dm_thread_ts:
            run_channel = dm_channel_id
            run_thread_ts = dm_thread_ts
            logger.info(f"정주행 DM 모드: channel={dm_channel_id}, thread_ts={dm_thread_ts}")
        else:
            # 폴백: notify_channel에 전송
            run_channel = self.notify_channel
            try:
                card_preview = "\n".join([f"  • {c.name}" for c in cards[:5]])
                if len(cards) > 5:
                    card_preview += f"\n  ... 외 {len(cards) - 5}개"

                msg_result = self.slack_client.chat_postMessage(
                    channel=self.notify_channel,
                    text=(
                        f"🚀 *리스트 정주행 시작*\n"
                        f"📋 리스트: *{list_name}*\n"
                        f"🎫 카드 수: {len(cards)}개\n"
                        f"🔖 세션 ID: `{session.session_id}`\n\n"
                        f"*처리할 카드:*\n{card_preview}"
                    )
                )
                run_thread_ts = msg_result["ts"]
                logger.info(f"정주행 시작 알림 전송 (폴백): thread_ts={run_thread_ts}")
            except Exception as e:
                logger.error(f"정주행 시작 알림 전송 실패: {e}")
                return

        # 정주행 세션 시작 (첫 번째 카드 처리)
        self._process_list_run_card(session.session_id, run_thread_ts, run_channel)

    def _process_list_run_card(self, session_id: str, thread_ts: str, run_channel: str = None):
        """리스트 정주행 카드 처리

        Args:
            session_id: 정주행 세션 ID
            thread_ts: 슬랙 스레드 타임스탬프
            run_channel: 메시지를 보낼 채널 (None이면 notify_channel로 폴백)
        """
        list_runner = self.list_runner_ref() if self.list_runner_ref else None
        if not list_runner:
            return

        channel = run_channel or self.notify_channel

        try:
            self._process_list_run_card_inner(
                list_runner, session_id, thread_ts, channel, run_channel
            )
        except Exception as e:
            logger.exception(
                f"정주행 카드 처리 중 미처리 예외 (Thread B): "
                f"session={session_id}, error={e}"
            )
            # 세션 일시 중단하여 체인 중단 원인을 추적할 수 있도록 함
            try:
                from seosoyoung.slackbot.trello.list_runner import SessionStatus
                list_runner.pause_run(session_id, f"미처리 예외: {e}")
            except Exception:
                pass
            # 슬랙 알림
            try:
                self.slack_client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=(
                        f"⚠️ 정주행 카드 처리 중 예기치 않은 오류가 발생했습니다.\n"
                        f"세션 ID: `{session_id}`\n오류: {e}"
                    )
                )
            except Exception:
                pass

    def _process_list_run_card_inner(
        self,
        list_runner,
        session_id: str,
        thread_ts: str,
        channel: str,
        run_channel: str = None,
    ):
        """_process_list_run_card의 실제 로직 (전역 try-except로 감싸기 위해 분리)"""
        from seosoyoung.slackbot.trello.list_runner import SessionStatus

        session = list_runner.get_session(session_id)
        if not session:
            logger.error(f"정주행 세션을 찾을 수 없습니다: {session_id}")
            return

        # 다음 카드 ID 조회
        next_card_id = list_runner.get_next_card_id(session_id)
        if not next_card_id:
            # 모든 카드 처리 완료
            list_runner.update_session_status(session_id, SessionStatus.COMPLETED)
            self.slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"✅ *리스트 정주행 완료*\n세션 ID: `{session_id}`"
            )
            logger.info(f"리스트 정주행 완료: {session_id}")
            return

        # 세션 상태를 RUNNING으로 변경
        list_runner.update_session_status(session_id, SessionStatus.RUNNING)

        # 카드 정보 조회
        card = self.trello.get_card(next_card_id)
        if not card:
            logger.error(f"카드를 찾을 수 없습니다: {next_card_id}")
            list_runner.mark_card_processed(session_id, next_card_id, "skipped")
            # 다음 카드로 진행
            self._process_list_run_card(session_id, thread_ts, run_channel)
            return

        # 카드를 In Progress로 이동
        in_progress_list_id = Config.trello.in_progress_list_id
        if in_progress_list_id:
            self.trello.move_card(card.id, in_progress_list_id)

        # 🌀 prefix 추가
        self._add_spinner_prefix(card)

        # 진행 상황 알림
        progress = f"{session.current_index + 1}/{len(session.card_ids)}"
        self.slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"▶️ [{progress}] <{card.url}|{card.name}>"
        )

        # Claude 세션 생성 및 실행
        claude_session = self.session_manager.create(
            thread_ts=thread_ts,
            channel_id=channel,
            user_id="list_runner",
            username="list_runner",
            role="admin"
        )

        # 프롬프트 생성
        prompt = self.prompt_builder.build_list_run(card, session_id, session.current_index + 1, len(session.card_ids))

        # DM 스레드 생성 (사고 과정 출력용) — 정주행 채널이 이미 DM이면 별도 DM 불필요
        if channel != self.notify_channel:
            # 이미 DM 채널에서 실행 중이므로 별도 DM 불필요
            dm_channel_id, dm_thread_ts = channel, thread_ts
        else:
            dm_channel_id, dm_thread_ts = self._open_dm_thread(card.name, card.url)

        # TrackedCard 생성 및 _tracked 등록 (To Go 감지와 중복 방지)
        tracked = TrackedCard(
            card_id=card.id,
            card_name=card.name,
            card_url=card.url,
            list_id=card.list_id,
            list_key="list_run",
            thread_ts=thread_ts,
            channel_id=channel,
            detected_at=datetime.now().isoformat(),
            has_execute=True,
        )
        self._tracked[card.id] = tracked
        self._save_tracked()

        def on_success():
            list_runner.mark_card_processed(session_id, card.id, "completed")
            self._remove_spinner_prefix(card.id, f"🌀 {card.name}")
            self._untrack_card(card.id)
            # _preemptive_compact 실패해도 체인이 끊기지 않도록 격리
            try:
                self._preemptive_compact(thread_ts, channel, card.name)
            except Exception as compact_err:
                logger.warning(
                    f"선제적 컴팩트 실패 (체인 계속): card={card.name}, error={compact_err}"
                )
            # 다음 카드 처리 (별도 스레드로)
            next_thread = threading.Thread(
                target=self._process_list_run_card,
                args=(session_id, thread_ts, run_channel),
                daemon=True
            )
            next_thread.start()

        def on_error(e):
            list_runner.mark_card_processed(session_id, card.id, "failed")
            list_runner.pause_run(session_id, str(e))
            self._remove_spinner_prefix(card.id, f"🌀 {card.name}")
            self._untrack_card(card.id)
            logger.error(
                f"정주행 카드 실패 (체인 중단): card={card.name}, "
                f"session={session_id}, index={session.current_index}, error={e}"
            )
            self.slack_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=(
                    f"❌ 카드 처리 실패: {card.name}\n"
                    f"세션: `{session_id}` | 인덱스: {session.current_index}\n"
                    f"오류: {e}"
                )
            )

        self._spawn_claude_thread(
            session=claude_session,
            prompt=prompt,
            thread_ts=thread_ts,
            channel=channel,
            tracked=tracked,
            dm_channel_id=dm_channel_id,
            dm_thread_ts=dm_thread_ts,
            on_success=on_success,
            on_error=on_error,
        )

