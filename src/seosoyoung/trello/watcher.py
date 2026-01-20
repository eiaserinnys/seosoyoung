"""Trello 워처 - To Plan / To Go 리스트 감시"""

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
    """추적 중인 카드 정보"""
    card_id: str
    card_name: str
    list_id: str
    list_key: str  # "to_plan" or "to_go"
    thread_ts: str
    channel_id: str
    detected_at: str


class TrelloWatcher:
    """Trello 리스트 감시자

    To Plan, To Go 리스트에 새 카드가 들어오면:
    1. Slack에 알림 메시지 전송
    2. 스레드 생성
    3. Claude Code 세션 시작
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

        # 추적 중인 카드
        self._tracked: dict[str, TrackedCard] = {}
        self._load_tracked()

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

        # 2. 더 이상 감시 리스트에 없는 카드 정리
        removed = []
        for card_id in self._tracked:
            if card_id not in current_cards:
                removed.append(card_id)

        for card_id in removed:
            tracked = self._tracked.pop(card_id)
            logger.info(f"카드 추적 해제: {tracked.card_name} (리스트 이동)")

        if removed:
            self._save_tracked()

        # 3. Review 리스트에서 dueComplete된 카드를 Done으로 이동
        self._check_review_list_for_completion()

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
                            text=f"✅ <{card.url}|*{card.name}*> 완료 처리됨 (Review → Done)"
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

    def _handle_new_card(self, card: TrelloCard, list_key: str):
        """새 카드 처리: 알림 → 🌀 추가 → 스레드 생성 → Claude 실행"""
        # 리스트 이름 매핑
        list_names = {
            "to_plan": "📋 To Plan",
            "to_go": "🚀 To Go",
        }
        list_name = list_names.get(list_key, list_key)

        # 1. 알림 메시지 전송 (간결한 형식)
        # 설명 첫 줄 추출 (있으면)
        desc_first_line = ""
        if card.desc:
            first_line = card.desc.strip().split("\n")[0]
            if first_line:
                desc_first_line = f"\n{first_line}"

        try:
            msg_result = self.slack_client.chat_postMessage(
                channel=self.notify_channel,
                text=f"*{list_name}에* <{card.url}|*{card.name}*> *감지*{desc_first_line}"
            )
            thread_ts = msg_result["ts"]
            logger.info(f"알림 전송 완료: thread_ts={thread_ts}")
        except Exception as e:
            logger.error(f"알림 전송 실패: {e}")
            return

        # 2. 🌀 prefix 추가 (슬랙 메시지 전송 후)
        if self._add_spinner_prefix(card):
            logger.info(f"🌀 prefix 추가: {card.name}")
        else:
            logger.warning(f"🌀 prefix 추가 실패: {card.name}")

        # 2. 추적 등록
        tracked = TrackedCard(
            card_id=card.id,
            card_name=card.name,
            list_id=card.list_id,
            list_key=list_key,
            thread_ts=thread_ts,
            channel_id=self.notify_channel,
            detected_at=datetime.now().isoformat(),
        )
        self._tracked[card.id] = tracked
        self._save_tracked()

        # 3. 세션 생성
        session = self.session_manager.create(
            thread_ts=thread_ts,
            channel_id=self.notify_channel,
            user_id="trello_watcher",
            username="trello_watcher",
            role="admin"  # 워처는 admin 권한으로 실행
        )

        # 4. 프롬프트 생성
        if list_key == "to_plan":
            prompt = self._build_to_plan_prompt(card)
        else:
            prompt = self._build_to_go_prompt(card)

        # 5. Claude 실행 (별도 스레드에서)
        # 🌀 제거를 위해 카드 정보 캡처
        card_id_for_cleanup = card.id
        card_name_with_spinner = f"🌀 {card.name}"

        def run_claude():
            # 락을 스레드 내부에서 획득 (같은 스레드에서 획득/해제해야 RLock이 정상 동작)
            # 이렇게 하면 _run_claude_in_session에서 같은 스레드로 RLock 재진입 가능
            lock = None
            if self.get_session_lock:
                lock = self.get_session_lock(thread_ts)
                lock.acquire()
                logger.debug(f"워처 락 획득: thread_ts={thread_ts}")
            try:
                # say 함수 생성 (thread_ts 고정)
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
                    client=self.slack_client
                )
            except Exception as e:
                logger.exception(f"Claude 실행 오류 (워처): {e}")
            finally:
                # Claude 실행 완료 후 🌀 제거
                if self._remove_spinner_prefix(card_id_for_cleanup, card_name_with_spinner):
                    logger.info(f"🌀 prefix 제거: {card.name}")
                else:
                    logger.warning(f"🌀 prefix 제거 실패: {card.name}")
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
제목, 본문과 함께 체크리스트와 코멘트를 확인하세요.
"""

    def _build_to_plan_prompt(self, card: TrelloCard) -> str:
        """To Plan 카드용 프롬프트 생성"""
        prompt = f"""📋 To Plan 리스트에 들어온 '{card.name}' 태스크의 계획을 수립해주세요.

카드 ID: {card.id}
카드 URL: {card.url}
{self._build_task_context_hint()}"""
        if card.desc:
            prompt += f"""
---
{card.desc}
---
"""
        return prompt

    def _build_to_go_prompt(self, card: TrelloCard) -> str:
        """To Go 카드용 프롬프트 생성"""
        prompt = f"""🚀 To Go 리스트에 들어온 '{card.name}' 태스크를 실행해주세요.

카드 ID: {card.id}
카드 URL: {card.url}
{self._build_task_context_hint()}"""
        if card.desc:
            prompt += f"""
---
{card.desc}
---
"""
        return prompt
