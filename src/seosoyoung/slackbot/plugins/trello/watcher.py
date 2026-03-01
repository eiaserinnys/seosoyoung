"""Trello 워처 - To Go 리스트 감시 및 처리

Config 싱글턴 의존성 없이, 생성자에서 설정을 직접 받습니다.
"""

import concurrent.futures
import json
import logging
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from seosoyoung.slackbot.plugins.trello.client import TrelloClient, TrelloCard
from seosoyoung.slackbot.plugins.trello.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


@dataclass
class TrackedCard:
    """추적 중인 카드 정보 (To Go 리스트 감시용)"""
    card_id: str
    card_name: str
    card_url: str
    list_id: str
    list_key: str
    thread_ts: str
    channel_id: str
    detected_at: str
    session_id: Optional[str] = None
    has_execute: bool = False
    dm_thread_ts: Optional[str] = None


@dataclass
class ThreadCardInfo:
    """스레드 ↔ 카드 매핑 정보 (리액션 처리용)"""
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

    모든 설정은 생성자에서 직접 전달받습니다.
    Config 싱글턴에 의존하지 않습니다.
    """

    def __init__(
        self,
        *,
        trello_client: TrelloClient,
        prompt_builder: PromptBuilder,
        slack_client,
        session_manager,
        claude_runner_factory: Callable,
        config: dict,
        get_session_lock: Optional[Callable[[str], threading.Lock]] = None,
        data_dir: Optional[Path] = None,
        list_runner_ref: Optional[Callable] = None,
    ):
        """
        Args:
            trello_client: TrelloClient 인스턴스
            prompt_builder: PromptBuilder 인스턴스
            slack_client: Slack WebClient
            session_manager: SessionManager 인스턴스
            claude_runner_factory: Claude 실행 팩토리
            config: 플러그인 설정 dict (YAML에서 로드)
            get_session_lock: 스레드별 락 반환 함수
            data_dir: 상태 파일 저장 디렉토리
            list_runner_ref: ListRunner 참조 함수
        """
        self.slack_client = slack_client
        self.session_manager = session_manager
        self.claude_runner_factory = claude_runner_factory
        self.get_session_lock = get_session_lock
        self.list_runner_ref = list_runner_ref

        self.trello = trello_client
        self.prompt_builder = prompt_builder

        # config에서 설정값 직접 읽기 (기본값 없이 — yaml에 명시)
        self.notify_channel = config["notify_channel"]
        self.poll_interval = config["poll_interval"]
        self.watch_lists = config["watch_lists"]
        self.dm_target_user_id = config["dm_target_user_id"]
        self.polling_debug = config["polling_debug"]

        # 리스트 IDs
        self._list_ids = config["list_ids"]

        # 상태 저장 경로
        self.data_dir = data_dir or Path.cwd() / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tracked_file = self.data_dir / "tracked_cards.json"
        self.thread_cards_file = self.data_dir / "thread_cards.json"

        # 추적 중인 카드
        self._tracked: dict[str, TrackedCard] = {}
        self._load_tracked()

        # 스레드 ↔ 카드 매핑
        self._thread_cards: dict[str, ThreadCardInfo] = {}
        self._load_thread_cards()

        # 워처 스레드
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._paused = False
        self._pause_lock = threading.Lock()

        # 리스트 정주행 직렬화 락
        self._list_run_lock = threading.Lock()

    # -- 상태 관리 메서드 (변경 없음) --

    def _load_tracked(self):
        """추적 상태 로드"""
        if self.tracked_file.exists():
            try:
                data = json.loads(self.tracked_file.read_text(encoding="utf-8"))
                for card_id, card_data in data.items():
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
        """카드 추적 해제"""
        if card_id in self._tracked:
            tracked = self._tracked.pop(card_id)
            self._save_tracked()
            logger.info(f"카드 추적 해제: {tracked.card_name}")

    def update_thread_card_session_id(self, thread_ts: str, session_id: str) -> bool:
        """ThreadCardInfo의 session_id 업데이트"""
        if thread_ts in self._thread_cards:
            self._thread_cards[thread_ts].session_id = session_id
            self._save_thread_cards()
            return True
        return False

    def get_tracked_by_thread_ts(self, thread_ts: str) -> Optional[ThreadCardInfo]:
        """thread_ts로 ThreadCardInfo 조회"""
        return self._thread_cards.get(thread_ts)

    def update_tracked_session_id(self, card_id: str, session_id: str) -> bool:
        """TrackedCard의 session_id 업데이트"""
        if card_id in self._tracked:
            self._tracked[card_id].session_id = session_id
            self._save_tracked()
            return True
        return False

    # -- 워처 라이프사이클 --

    def start(self):
        """워처 시작"""
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
        """워처 일시 중단"""
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
        with self._pause_lock:
            return self._paused

    def _run(self):
        """워처 메인 루프"""
        while not self._stop_event.is_set():
            try:
                self._poll()
            except Exception as e:
                logger.exception(f"워처 폴링 오류: {e}")
            self._stop_event.wait(timeout=self.poll_interval)

    def _poll(self):
        """리스트 폴링"""
        if self.is_paused:
            logger.debug("Trello 워처 일시 중단 상태 - 폴링 스킵")
            return

        if self.polling_debug:
            logger.debug("Trello 폴링 시작")

        current_cards: dict[str, tuple[TrelloCard, str]] = {}
        for list_key, list_id in self.watch_lists.items():
            cards = self.trello.get_cards_in_list(list_id)
            for card in cards:
                current_cards[card.id] = (card, list_key)

        self._cleanup_stale_tracked(current_cards)

        for card_id, (card, list_key) in current_cards.items():
            if card_id not in self._tracked:
                logger.info(f"새 카드 감지: [{list_key}] {card.name}")
                self._handle_new_card(card, list_key)

        self._check_review_list_for_completion()
        self._check_run_list_labels()

    STALE_THRESHOLD = timedelta(hours=2)

    def _cleanup_stale_tracked(self, current_cards: dict[str, tuple]):
        """만료된 _tracked 항목 정리"""
        now = datetime.now()
        stale_ids = []
        for card_id, tracked in self._tracked.items():
            try:
                detected = datetime.fromisoformat(tracked.detected_at)
            except (ValueError, TypeError):
                detected = now
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

    def _check_review_list_for_completion(self):
        """Review 리스트에서 dueComplete된 카드를 Done으로 자동 이동"""
        review_list_id = self._list_ids.get("review")
        done_list_id = self._list_ids.get("done")

        if not review_list_id or not done_list_id:
            return

        cards = self.trello.get_cards_in_list(review_list_id)
        for card in cards:
            if card.due_complete:
                logger.info(f"dueComplete 카드 감지: {card.name} -> Done으로 이동")
                if self.trello.move_card(card.id, done_list_id):
                    logger.info(f"카드 이동 완료: {card.name}")
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

    # -- 유틸리티 메서드 --

    def _add_spinner_prefix(self, card: TrelloCard) -> bool:
        if card.name.startswith("🌀"):
            return True
        new_name = f"🌀 {card.name}"
        return self.trello.update_card_name(card.id, new_name)

    def _remove_spinner_prefix(self, card_id: str, card_name: str) -> bool:
        if not card_name.startswith("🌀"):
            return True
        new_name = card_name.lstrip("🌀").lstrip()
        return self.trello.update_card_name(card_id, new_name)

    def _has_execute_label(self, card: TrelloCard) -> bool:
        for label in card.labels:
            if label.get("name", "").lower() == "execute":
                return True
        return False

    def _has_run_list_label(self, card: TrelloCard) -> bool:
        for label in card.labels:
            if label.get("name", "") == "🏃 Run List":
                return True
        return False

    def _get_run_list_label_id(self, card: TrelloCard) -> Optional[str]:
        for label in card.labels:
            if label.get("name", "") == "🏃 Run List":
                return label.get("id")
        return None

    def _build_header(self, card_name: str, card_url: str, session_id: str = "") -> str:
        session_display = f" | #️⃣ {session_id[:8]}" if session_id else ""
        return f"*🎫 <{card_url}|{card_name}>{session_display}*"

    def _get_dm_or_notify_channel(self) -> str:
        if self.dm_target_user_id:
            try:
                dm_result = self.slack_client.conversations_open(users=self.dm_target_user_id)
                return dm_result["channel"]["id"]
            except Exception as e:
                logger.warning(f"DM 채널 열기 실패 (notify_channel로 폴백): {e}")
        return self.notify_channel

    def _open_dm_thread(self, card_name: str, card_url: str) -> tuple[Optional[str], Optional[str]]:
        if not self.dm_target_user_id:
            return None, None
        try:
            dm_result = self.slack_client.conversations_open(users=self.dm_target_user_id)
            dm_channel_id = dm_result["channel"]["id"]
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
            logger.warning(f"DM 스레드 생성 실패: {e}")
            return None, None

    # -- 카드 처리 --

    def _handle_new_card(self, card: TrelloCard, list_key: str):
        """새 카드 처리: In Progress 이동 → 알림 → 🌀 추가 → Claude 실행"""
        in_progress_list_id = self._list_ids.get("in_progress")
        if in_progress_list_id:
            if self.trello.move_card(card.id, in_progress_list_id):
                logger.info(f"카드 In Progress로 이동: {card.name}")
            else:
                logger.warning(f"카드 In Progress 이동 실패: {card.name}")

        has_execute = self._has_execute_label(card)
        dm_channel_id, dm_thread_ts = self._open_dm_thread(card.name, card.url)

        if dm_channel_id and dm_thread_ts:
            thread_ts = dm_thread_ts
            msg_channel = dm_channel_id
            logger.info(f"DM 모드: channel={dm_channel_id}, thread_ts={dm_thread_ts}")
        else:
            header = self._build_header(card.name, card.url)
            initial_text = f"{header}\n\n`소영이 생각합니다...`"
            try:
                msg_result = self.slack_client.chat_postMessage(
                    channel=self.notify_channel, text=initial_text
                )
                thread_ts = msg_result["ts"]
                msg_channel = self.notify_channel
                logger.info(f"알림 전송 완료 (폴백): thread_ts={thread_ts}")
                reaction = "arrow_forward" if has_execute else "thought_balloon"
                try:
                    self.slack_client.reactions_add(
                        channel=self.notify_channel, timestamp=thread_ts, name=reaction
                    )
                except Exception as e:
                    logger.debug(f"초기 상태 리액션 추가 실패: {e}")
            except Exception as e:
                logger.error(f"알림 전송 실패: {e}")
                return

        if self._add_spinner_prefix(card):
            logger.info(f"🌀 prefix 추가: {card.name}")
        else:
            logger.warning(f"🌀 prefix 추가 실패: {card.name}")

        tracked = TrackedCard(
            card_id=card.id, card_name=card.name, card_url=card.url,
            list_id=card.list_id, list_key=list_key,
            thread_ts=thread_ts, channel_id=msg_channel,
            detected_at=datetime.now().isoformat(), has_execute=has_execute,
        )
        tracked.dm_thread_ts = dm_thread_ts
        self._tracked[card.id] = tracked
        self._save_tracked()
        self._register_thread_card(tracked)

        session = self.session_manager.create(
            thread_ts=thread_ts, channel_id=msg_channel,
            user_id="trello_watcher", username="trello_watcher", role="admin"
        )

        prompt = self.prompt_builder.build_to_go(card, has_execute)
        card_id_for_cleanup = card.id
        card_name_with_spinner = f"🌀 {card.name}"

        def on_finally():
            if self._remove_spinner_prefix(card_id_for_cleanup, card_name_with_spinner):
                logger.info(f"🌀 prefix 제거: {card.name}")
            else:
                logger.warning(f"🌀 prefix 제거 실패: {card.name}")
            self._untrack_card(card_id_for_cleanup)

        self._spawn_claude_thread(
            session=session, prompt=prompt, thread_ts=thread_ts,
            channel=msg_channel, tracked=tracked,
            dm_channel_id=dm_channel_id, dm_thread_ts=dm_thread_ts,
            on_finally=on_finally,
        )

    def build_reaction_execute_prompt(self, info: ThreadCardInfo) -> str:
        """하위 호환: PromptBuilder에 위임"""
        return self.prompt_builder.build_reaction_execute(info)

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
        """Claude 실행 스레드 스포닝"""
        from seosoyoung.slackbot.presentation.types import PresentationContext
        from seosoyoung.slackbot.presentation.progress import build_progress_callbacks
        from seosoyoung.slackbot.slack.formatting import update_message

        def run_claude():
            claude_succeeded = False
            try:
                def say(text, thread_ts=None, **kwargs):
                    self.slack_client.chat_postMessage(
                        channel=channel,
                        thread_ts=thread_ts or tracked.thread_ts,
                        text=text
                    )

                pctx = PresentationContext(
                    channel=channel, thread_ts=thread_ts, msg_ts=thread_ts,
                    say=say, client=self.slack_client, effective_role="admin",
                    session_id=session.session_id, user_id="trello_watcher",
                    last_msg_ts=thread_ts, main_msg_ts=thread_ts,
                    trello_card=tracked, is_trello_mode=True,
                    dm_channel_id=dm_channel_id, dm_thread_ts=dm_thread_ts,
                )

                on_progress, on_compact = build_progress_callbacks(pctx, update_message)

                self.claude_runner_factory(
                    prompt=prompt, thread_ts=thread_ts, msg_ts=thread_ts,
                    on_progress=on_progress, on_compact=on_compact,
                    presentation=pctx, session_id=session.session_id, role="admin",
                )
                claude_succeeded = True
            except Exception as e:
                logger.exception(f"Claude 실행 오류 (워처): {e}")
                if on_error:
                    on_error(e)

            if on_finally:
                try:
                    on_finally()
                except Exception as e:
                    logger.exception(f"on_finally 콜백 오류: {e}")

            if claude_succeeded and on_success:
                try:
                    on_success()
                except Exception as e:
                    logger.exception(f"on_success 콜백 오류: {e}")

        claude_thread = threading.Thread(target=run_claude, daemon=True)
        claude_thread.start()

    # -- 리스트 정주행 --

    def _get_operational_list_ids(self) -> set[str]:
        """운영 리스트 ID 집합 반환"""
        ids = set()
        for list_id in self.watch_lists.values():
            if list_id:
                ids.add(list_id)
        for list_id in self._list_ids.values():
            if list_id:
                ids.add(list_id)
        return ids

    def _check_run_list_labels(self):
        """🏃 Run List 레이블을 가진 카드 감지 및 리스트 정주행 시작"""
        lists = self.trello.get_lists()
        operational_ids = self._get_operational_list_ids()

        for lst in lists:
            list_id = lst["id"]
            list_name = lst["name"]
            if list_id in operational_ids:
                continue

            cards = self.trello.get_cards_in_list(list_id)
            if not cards:
                continue

            first_card = cards[0]
            if not self._has_run_list_label(first_card):
                continue

            logger.info(f"🏃 Run List 레이블 감지: {list_name} - {first_card.name}")

            with self._list_run_lock:
                list_runner = self.list_runner_ref() if self.list_runner_ref else None
                if list_runner:
                    active_sessions = list_runner.get_active_sessions()
                    already_running = any(s.list_id == list_id for s in active_sessions)
                    if already_running:
                        logger.warning(f"이미 활성 정주행 세션이 있어 스킵: {list_name}")
                        continue

                label_id = self._get_run_list_label_id(first_card)
                if label_id:
                    if self.trello.remove_label_from_card(first_card.id, label_id):
                        logger.info(f"🏃 Run List 레이블 제거: {first_card.name}")
                    else:
                        logger.warning(f"레이블 제거 실패, 정주행 스킵: {first_card.name}")
                        continue
                else:
                    logger.warning(f"레이블 ID를 찾을 수 없음: {first_card.name}")
                    continue

                self._start_list_run(list_id, list_name, cards)

    COMPACT_TIMEOUT_SECONDS = 60

    def _preemptive_compact(self, thread_ts: str, channel: str, card_name: str):
        """카드 완료 후 선제적 컨텍스트 컴팩트"""
        session = self.session_manager.get(thread_ts)
        if not session or not session.session_id:
            logger.warning(f"선제적 컴팩트 스킵: 세션 없음 (card={card_name})")
            return

        try:
            from seosoyoung.slackbot.claude.agent_runner import ClaudeRunner
            runner = ClaudeRunner()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(runner.run_sync, runner.compact_session(session.session_id))
                try:
                    result = future.result(timeout=self.COMPACT_TIMEOUT_SECONDS)
                except concurrent.futures.TimeoutError:
                    logger.warning(
                        f"선제적 컴팩트 타임아웃 ({self.COMPACT_TIMEOUT_SECONDS}s): card={card_name}"
                    )
                    return

            if result.success:
                logger.info(f"선제적 컴팩트 완료: card={card_name}")
                if result.session_id and result.session_id != session.session_id:
                    self.session_manager.update_session_id(thread_ts, result.session_id)
            else:
                logger.warning(f"선제적 컴팩트 실패: card={card_name}, error={result.error}")
        except Exception as e:
            logger.warning(f"선제적 컴팩트 예외: card={card_name}, {e}")

    def _start_list_run(self, list_id: str, list_name: str, cards: list[TrelloCard]):
        """리스트 정주행 시작"""
        logger.info(f"리스트 정주행 시작: {list_name} ({len(cards)}개 카드)")

        list_runner = self.list_runner_ref() if self.list_runner_ref else None
        if not list_runner:
            logger.warning("ListRunner가 설정되지 않아 정주행을 시작할 수 없습니다.")
            return

        card_ids = [card.id for card in cards]
        session = list_runner.create_session(
            list_id=list_id, list_name=list_name, card_ids=card_ids,
        )

        dm_channel_id, dm_thread_ts = self._open_dm_thread(f"📋 {list_name} 정주행", "")

        if dm_channel_id and dm_thread_ts:
            run_channel = dm_channel_id
            run_thread_ts = dm_thread_ts
        else:
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
            except Exception as e:
                logger.error(f"정주행 시작 알림 전송 실패: {e}")
                return

        self._process_list_run_card(session.session_id, run_thread_ts, run_channel)

    def _process_list_run_card(self, session_id: str, thread_ts: str, run_channel: str = None):
        """리스트 정주행 카드 처리"""
        list_runner = self.list_runner_ref() if self.list_runner_ref else None
        if not list_runner:
            return

        channel = run_channel or self.notify_channel

        try:
            self._process_list_run_card_inner(
                list_runner, session_id, thread_ts, channel, run_channel
            )
        except Exception as e:
            logger.exception(f"정주행 카드 처리 중 미처리 예외: session={session_id}, error={e}")
            try:
                from seosoyoung.slackbot.plugins.trello.list_runner import SessionStatus
                list_runner.pause_run(session_id, f"미처리 예외: {e}")
            except Exception:
                pass
            try:
                self.slack_client.chat_postMessage(
                    channel=channel, thread_ts=thread_ts,
                    text=f"⚠️ 정주행 카드 처리 중 오류.\n세션 ID: `{session_id}`\n오류: {e}"
                )
            except Exception:
                pass

    def _process_list_run_card_inner(
        self, list_runner, session_id: str, thread_ts: str,
        channel: str, run_channel: str = None,
    ):
        from seosoyoung.slackbot.plugins.trello.list_runner import SessionStatus

        session = list_runner.get_session(session_id)
        if not session:
            logger.error(f"정주행 세션을 찾을 수 없습니다: {session_id}")
            return

        next_card_id = list_runner.get_next_card_id(session_id)
        if not next_card_id:
            list_runner.update_session_status(session_id, SessionStatus.COMPLETED)
            self.slack_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text=f"✅ *리스트 정주행 완료*\n세션 ID: `{session_id}`"
            )
            logger.info(f"리스트 정주행 완료: {session_id}")
            return

        list_runner.update_session_status(session_id, SessionStatus.RUNNING)

        if next_card_id in self._tracked:
            existing = self._tracked[next_card_id]
            if existing.thread_ts != thread_ts:
                logger.warning(f"카드가 다른 세션에서 이미 처리 중이므로 스킵: {next_card_id}")
                list_runner.mark_card_processed(session_id, next_card_id, "skipped_duplicate")
                self._process_list_run_card(session_id, thread_ts, run_channel)
                return

        card = self.trello.get_card(next_card_id)
        if not card:
            logger.error(f"카드를 찾을 수 없습니다: {next_card_id}")
            list_runner.mark_card_processed(session_id, next_card_id, "skipped")
            self._process_list_run_card(session_id, thread_ts, run_channel)
            return

        in_progress_list_id = self._list_ids.get("in_progress")
        if in_progress_list_id:
            self.trello.move_card(card.id, in_progress_list_id)

        self._add_spinner_prefix(card)

        progress = f"{session.current_index + 1}/{len(session.card_ids)}"
        self.slack_client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            text=f"▶️ [{progress}] <{card.url}|{card.name}>"
        )

        claude_session = self.session_manager.create(
            thread_ts=thread_ts, channel_id=channel,
            user_id="list_runner", username="list_runner", role="admin"
        )

        prompt = self.prompt_builder.build_list_run(
            card, session_id, session.current_index + 1, len(session.card_ids)
        )

        if channel != self.notify_channel:
            dm_channel_id, dm_thread_ts = channel, thread_ts
        else:
            dm_channel_id, dm_thread_ts = self._open_dm_thread(card.name, card.url)

        tracked = TrackedCard(
            card_id=card.id, card_name=card.name, card_url=card.url,
            list_id=card.list_id, list_key="list_run",
            thread_ts=thread_ts, channel_id=channel,
            detected_at=datetime.now().isoformat(), has_execute=True,
        )
        self._tracked[card.id] = tracked
        self._save_tracked()

        def on_success():
            list_runner.mark_card_processed(session_id, card.id, "completed")
            self._remove_spinner_prefix(card.id, f"🌀 {card.name}")
            self._untrack_card(card.id)
            try:
                self._preemptive_compact(thread_ts, channel, card.name)
            except Exception as compact_err:
                logger.warning(f"선제적 컴팩트 실패: card={card.name}, error={compact_err}")
            next_thread = threading.Thread(
                target=self._process_list_run_card,
                args=(session_id, thread_ts, run_channel), daemon=True
            )
            next_thread.start()

        def on_error(e):
            list_runner.mark_card_processed(session_id, card.id, "failed")
            list_runner.pause_run(session_id, str(e))
            self._remove_spinner_prefix(card.id, f"🌀 {card.name}")
            self._untrack_card(card.id)
            logger.error(f"정주행 카드 실패: card={card.name}, session={session_id}")
            self.slack_client.chat_postMessage(
                channel=channel, thread_ts=thread_ts,
                text=f"❌ 카드 처리 실패: {card.name}\n세션: `{session_id}` | 오류: {e}"
            )

        self._spawn_claude_thread(
            session=claude_session, prompt=prompt, thread_ts=thread_ts,
            channel=channel, tracked=tracked,
            dm_channel_id=dm_channel_id, dm_thread_ts=dm_thread_ts,
            on_success=on_success, on_error=on_error,
        )
