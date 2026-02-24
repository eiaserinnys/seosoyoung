"""채널 소화 주기적 스케줄러

버퍼에 메시지가 쌓여 있지만 임계치에 도달하지 못한 경우,
일정 주기(기본 5분)마다 소화 파이프라인을 트리거합니다.
"""

import asyncio
import logging
import threading

from seosoyoung.memory.channel_intervention import InterventionHistory
from seosoyoung.memory.channel_observer import ChannelObserver, DigestCompressor
from seosoyoung.memory.channel_store import ChannelStore

logger = logging.getLogger(__name__)


class ChannelDigestScheduler:
    """주기적으로 채널 버퍼를 체크하여 소화를 트리거하는 스케줄러

    threading.Timer를 사용하여 interval_sec 간격으로 실행합니다.
    버퍼에 토큰이 1개 이상 있으면 소화 파이프라인을 실행합니다.
    (buffer_threshold=1로 호출하여 임계치 무관하게 동작)
    """

    def __init__(
        self,
        *,
        store: ChannelStore,
        observer: ChannelObserver,
        compressor: DigestCompressor | None,
        cooldown: InterventionHistory,
        slack_client,
        channels: list[str],
        interval_sec: int = 300,
        buffer_threshold: int = 30000,
        digest_max_tokens: int = 10000,
        digest_target_tokens: int = 5000,
        debug_channel: str = "",
        intervention_threshold: float = 0.3,
        mention_tracker=None,
        **kwargs,
    ):
        self.store = store
        self.observer = observer
        self.compressor = compressor
        self.cooldown = cooldown
        self.slack_client = slack_client
        self.channels = channels
        self.interval_sec = interval_sec
        self.buffer_threshold = buffer_threshold
        self.digest_max_tokens = digest_max_tokens
        self.digest_target_tokens = digest_target_tokens
        self.debug_channel = debug_channel
        self.intervention_threshold = intervention_threshold
        self.mention_tracker = mention_tracker

        self._timer: threading.Timer | None = None
        self._running = False

    def start(self) -> None:
        """스케줄러를 시작합니다."""
        if self._running:
            return
        self._running = True
        self._schedule_next()
        logger.info(
            f"채널 소화 스케줄러 시작: {self.interval_sec}초 간격, "
            f"채널 {len(self.channels)}개"
        )

    def stop(self) -> None:
        """스케줄러를 중지합니다."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("채널 소화 스케줄러 중지")

    def _schedule_next(self) -> None:
        """다음 실행을 예약합니다."""
        if not self._running:
            return
        self._timer = threading.Timer(self.interval_sec, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """주기적 실행: 각 채널의 버퍼를 체크하고 소화를 트리거합니다."""
        try:
            self._check_and_digest()
        except Exception as e:
            logger.error(f"주기적 소화 체크 실패: {e}")
        finally:
            self._schedule_next()

    def _check_and_digest(self) -> None:
        """모든 관찰 채널의 pending 버퍼를 체크하여 파이프라인을 트리거합니다."""
        for channel_id in self.channels:
            try:
                pending_tokens = self.store.count_pending_tokens(channel_id)
                if pending_tokens <= 0:
                    continue

                # 이미 임계치를 초과한 경우 → 메시지 이벤트에서 트리거될 것이므로 스킵
                if pending_tokens >= self.buffer_threshold:
                    continue

                logger.info(
                    f"주기적 파이프라인 트리거 ({channel_id}): "
                    f"pending {pending_tokens} tok (임계치 미만)"
                )

                self._run_pipeline(channel_id)

            except Exception as e:
                logger.error(f"주기적 파이프라인 체크 실패 ({channel_id}): {e}")

    def _run_pipeline(self, channel_id: str) -> None:
        """소화/판단 파이프라인을 실행합니다."""
        from seosoyoung.memory.channel_pipeline import run_channel_pipeline
        from seosoyoung.claude import get_claude_runner
        from seosoyoung.config import Config

        runner = get_claude_runner()

        try:
            asyncio.run(
                run_channel_pipeline(
                    store=self.store,
                    observer=self.observer,
                    channel_id=channel_id,
                    slack_client=self.slack_client,
                    cooldown=self.cooldown,
                    threshold_a=1,  # 주기적 트리거는 pending이 있으면 무조건 실행
                    threshold_b=self.buffer_threshold,
                    compressor=self.compressor,
                    digest_max_tokens=self.digest_max_tokens,
                    digest_target_tokens=self.digest_target_tokens,
                    debug_channel=self.debug_channel,
                    intervention_threshold=self.intervention_threshold,
                    claude_runner=runner,
                    bot_user_id=Config.slack.bot_user_id,
                    mention_tracker=self.mention_tracker,
                )
            )
        except Exception as e:
            logger.error(f"주기적 파이프라인 실행 실패 ({channel_id}): {e}")
