"""채널 소화 주기적 스케줄러 테스트"""

import threading
import time
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from seosoyoung.slackbot.plugins.channel_observer.scheduler import ChannelDigestScheduler


@pytest.fixture
def mock_deps():
    """스케줄러 의존성 목 객체"""
    store = MagicMock()
    observer = MagicMock()
    compressor = MagicMock()
    cooldown = MagicMock()
    slack_client = MagicMock()

    return {
        "store": store,
        "observer": observer,
        "compressor": compressor,
        "cooldown": cooldown,
        "slack_client": slack_client,
    }


def make_scheduler(mock_deps, channels=None, interval_sec=60, **kwargs):
    """스케줄러 인스턴스를 생성합니다."""
    return ChannelDigestScheduler(
        store=mock_deps["store"],
        observer=mock_deps["observer"],
        compressor=mock_deps["compressor"],
        cooldown=mock_deps["cooldown"],
        slack_client=mock_deps["slack_client"],
        channels=channels or ["C001"],
        interval_sec=interval_sec,
        **kwargs,
    )


class TestSchedulerStartStop:
    """스케줄러 시작/중지 테스트"""

    def test_start_sets_running(self, mock_deps):
        scheduler = make_scheduler(mock_deps)
        scheduler.start()
        assert scheduler._running is True
        scheduler.stop()

    def test_stop_sets_not_running(self, mock_deps):
        scheduler = make_scheduler(mock_deps)
        scheduler.start()
        scheduler.stop()
        assert scheduler._running is False
        assert scheduler._timer is None

    def test_double_start_is_noop(self, mock_deps):
        scheduler = make_scheduler(mock_deps)
        scheduler.start()
        first_timer = scheduler._timer
        scheduler.start()
        assert scheduler._timer is first_timer
        scheduler.stop()

    def test_stop_without_start_is_safe(self, mock_deps):
        scheduler = make_scheduler(mock_deps)
        scheduler.stop()
        assert scheduler._running is False


class TestCheckAndDigest:
    """_check_and_digest 메서드 테스트"""

    def test_skips_empty_buffer(self, mock_deps):
        """버퍼가 비어 있으면 스킵합니다."""
        mock_deps["store"].count_pending_tokens.return_value = 0

        scheduler = make_scheduler(mock_deps, channels=["C001"])

        with patch.object(scheduler, "_run_pipeline") as mock_run:
            scheduler._check_and_digest()
            mock_run.assert_not_called()

    def test_skips_over_threshold(self, mock_deps):
        """임계치 이상이면 스킵합니다 (메시지 이벤트에서 처리)."""
        mock_deps["store"].count_pending_tokens.return_value = 50000

        scheduler = make_scheduler(
            mock_deps, channels=["C001"], buffer_threshold=30000
        )

        with patch.object(scheduler, "_run_pipeline") as mock_run:
            scheduler._check_and_digest()
            mock_run.assert_not_called()

    def test_triggers_under_threshold(self, mock_deps):
        """임계치 미만 & 버퍼 있으면 소화를 트리거합니다."""
        mock_deps["store"].count_pending_tokens.return_value = 100

        scheduler = make_scheduler(
            mock_deps, channels=["C001"], buffer_threshold=30000
        )

        with patch.object(scheduler, "_run_pipeline") as mock_run:
            scheduler._check_and_digest()
            mock_run.assert_called_once_with("C001")

    def test_multiple_channels(self, mock_deps):
        """여러 채널을 순회합니다."""
        mock_deps["store"].count_pending_tokens.side_effect = [100, 0, 200]

        scheduler = make_scheduler(
            mock_deps, channels=["C001", "C002", "C003"], buffer_threshold=30000
        )

        with patch.object(scheduler, "_run_pipeline") as mock_run:
            scheduler._check_and_digest()
            assert mock_run.call_count == 2
            mock_run.assert_any_call("C001")
            mock_run.assert_any_call("C003")

    def test_error_in_one_channel_does_not_block_others(self, mock_deps):
        """한 채널에서 오류가 발생해도 다른 채널 처리에 영향 없음."""
        mock_deps["store"].count_pending_tokens.side_effect = [
            Exception("test error"),
            100,
        ]

        scheduler = make_scheduler(
            mock_deps, channels=["C001", "C002"], buffer_threshold=30000
        )

        with patch.object(scheduler, "_run_pipeline") as mock_run:
            scheduler._check_and_digest()
            mock_run.assert_called_once_with("C002")


class TestRunDigest:
    """_run_pipeline 메서드 테스트"""

    def test_calls_pipeline_with_threshold_1(self, mock_deps):
        """buffer_threshold=1로 파이프라인을 호출합니다."""
        scheduler = make_scheduler(
            mock_deps,
            channels=["C001"],
            buffer_threshold=30000,
            debug_channel="D001",
            intervention_threshold=0.3,
        )

        with patch(
            "seosoyoung.slackbot.plugins.channel_observer.pipeline.run_channel_pipeline",
            new_callable=MagicMock,
        ):
            with patch(
                "seosoyoung.slackbot.plugins.channel_observer.scheduler.asyncio.run"
            ) as mock_asyncio_run:
                scheduler._run_pipeline("C001")
                mock_asyncio_run.assert_called_once()

    def test_pipeline_error_is_caught(self, mock_deps):
        """파이프라인 실행 오류가 캐치됩니다."""
        scheduler = make_scheduler(mock_deps, channels=["C001"])

        with patch(
            "seosoyoung.slackbot.plugins.channel_observer.scheduler.asyncio.run",
            side_effect=Exception("pipeline error"),
        ):
            # 예외가 전파되지 않아야 함
            scheduler._run_pipeline("C001")


class TestTick:
    """_tick 메서드 테스트"""

    def test_tick_reschedules(self, mock_deps):
        """_tick 실행 후 다음 실행이 예약됩니다."""
        scheduler = make_scheduler(mock_deps, channels=["C001"])
        scheduler._running = True

        mock_deps["store"].count_pending_tokens.return_value = 0

        with patch.object(scheduler, "_schedule_next") as mock_schedule:
            scheduler._tick()
            mock_schedule.assert_called_once()

    def test_tick_reschedules_even_on_error(self, mock_deps):
        """_check_and_digest에서 오류가 나도 다음 실행이 예약됩니다."""
        scheduler = make_scheduler(mock_deps, channels=["C001"])
        scheduler._running = True

        with patch.object(
            scheduler, "_check_and_digest", side_effect=Exception("tick error")
        ):
            with patch.object(scheduler, "_schedule_next") as mock_schedule:
                scheduler._tick()
                mock_schedule.assert_called_once()
