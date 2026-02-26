"""MentionTracker 단위 테스트 + collector/pipeline 통합 테스트

v2: 멘션 스레드도 수집(collect) + 소화(consume)는 정상 처리하되,
    리액션/개입만 필터링하는 방식으로 전환.
"""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from seosoyoung.slackbot.handlers.mention_tracker import MentionTracker
from seosoyoung.slackbot.handlers.channel_collector import ChannelMessageCollector
from seosoyoung.slackbot.memory.channel_store import ChannelStore
from seosoyoung.slackbot.memory.channel_intervention import InterventionHistory
from seosoyoung.slackbot.memory.channel_observer import JudgeItem, JudgeResult


@pytest.fixture
def tracker():
    return MentionTracker()


@pytest.fixture
def store(tmp_path):
    return ChannelStore(base_dir=tmp_path)


# ── MentionTracker 단위 테스트 ──────────────────────────

class TestMentionTracker:
    """MentionTracker 기본 동작 테스트"""

    def test_mark_and_is_handled(self, tracker):
        """마킹 후 is_handled가 True를 반환"""
        tracker.mark("1234.5678")
        assert tracker.is_handled("1234.5678") is True

    def test_not_handled_by_default(self, tracker):
        """마킹하지 않은 스레드는 False"""
        assert tracker.is_handled("9999.0000") is False

    def test_unmark(self, tracker):
        """unmark 후 is_handled가 False"""
        tracker.mark("1234.5678")
        tracker.unmark("1234.5678")
        assert tracker.is_handled("1234.5678") is False

    def test_unmark_nonexistent_no_error(self, tracker):
        """존재하지 않는 ts를 unmark해도 에러 없음"""
        tracker.unmark("not_exists")  # pop(, None)는 에러를 내지 않음

    def test_mark_empty_string_ignored(self, tracker):
        """빈 문자열은 마킹하지 않음"""
        tracker.mark("")
        assert tracker.is_handled("") is False

    def test_handled_count(self, tracker):
        """handled_count가 마킹 수를 반영"""
        assert tracker.handled_count == 0
        tracker.mark("a")
        tracker.mark("b")
        assert tracker.handled_count == 2
        tracker.unmark("a")
        assert tracker.handled_count == 1

    def test_mark_idempotent(self, tracker):
        """같은 ts를 여러 번 마킹해도 중복 없음"""
        tracker.mark("1234.5678")
        tracker.mark("1234.5678")
        assert tracker.handled_count == 1


# ── MentionTracker TTL 테스트 ───────────────────────────

class TestMentionTrackerTTL:
    """TTL 기반 자동 만료 테스트"""

    def test_ttl_expiration(self):
        """TTL 초과 시 자동으로 만료됨"""
        tracker = MentionTracker(ttl_seconds=0)  # 즉시 만료
        tracker.mark("1234.5678")
        # TTL=0이므로 다음 호출 시 만료
        time.sleep(0.01)
        assert tracker.is_handled("1234.5678") is False

    def test_ttl_not_expired_within_window(self):
        """TTL 내에서는 유효함"""
        tracker = MentionTracker(ttl_seconds=3600)  # 1시간
        tracker.mark("1234.5678")
        assert tracker.is_handled("1234.5678") is True

    def test_ttl_handled_count_after_expiry(self):
        """만료 후 handled_count가 감소함"""
        tracker = MentionTracker(ttl_seconds=0)
        tracker.mark("a")
        tracker.mark("b")
        time.sleep(0.01)
        assert tracker.handled_count == 0

    def test_re_mark_refreshes_ttl(self):
        """재마킹 시 TTL이 갱신됨"""
        tracker = MentionTracker(ttl_seconds=3600)
        tracker.mark("1234.5678")
        # 재마킹
        tracker.mark("1234.5678")
        assert tracker.is_handled("1234.5678") is True
        assert tracker.handled_count == 1

    def test_default_ttl_is_30_minutes(self):
        """기본 TTL이 30분(1800초)임"""
        tracker = MentionTracker()
        assert tracker._ttl_seconds == 1800

    def test_mixed_expired_and_active(self):
        """만료된 항목과 활성 항목이 공존할 때 올바르게 처리"""
        tracker = MentionTracker(ttl_seconds=0)
        tracker.mark("old")
        time.sleep(0.01)
        # old는 만료, new는 활성
        tracker._ttl_seconds = 3600  # TTL을 늘려서 new는 만료 안 되게
        tracker.mark("new")
        assert tracker.is_handled("old") is False
        assert tracker.is_handled("new") is True
        assert tracker.handled_count == 1


# ── Collector + MentionTracker 통합 테스트 ──────────────

class TestCollectorWithMentionTracker:
    """채널 수집기가 MentionTracker와 연동하여 멘션 스레드를 수집+마킹하는지 테스트

    v2 변경: 멘션 스레드 메시지도 정상 수집(collect=True)하되 마킹만 유지.
    리액션/개입 필터링은 파이프라인에서 처리합니다.
    """

    def test_collect_mention_handled_thread(self, store, tracker):
        """멘션으로 처리 중인 스레드 메시지도 정상 수집됨"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=tracker,
        )
        # 스레드를 멘션으로 마킹
        tracker.mark("1234.0000")

        # 해당 스레드의 후속 메시지 수집 시도
        event = {
            "channel": "C_OBS",
            "ts": "1234.9999",
            "user": "U001",
            "text": "스레드 후속 메시지",
            "thread_ts": "1234.0000",
        }
        result = collector.collect(event)
        assert result is True  # 수집됨 (v2: 스킵하지 않음)

        # 버퍼에 저장됨
        msgs = store.load_thread_buffer("C_OBS", "1234.0000")
        assert len(msgs) == 1
        assert msgs[0]["ts"] == "1234.9999"

    def test_collect_mention_handled_root_message(self, store, tracker):
        """멘션으로 처리 중인 채널 루트 메시지도 정상 수집됨"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=tracker,
        )
        # 루트 메시지 ts를 마킹 (채널에서 멘션한 경우)
        tracker.mark("1234.5678")

        event = {
            "channel": "C_OBS",
            "ts": "1234.5678",
            "user": "U001",
            "text": "<@BOT123> 질문입니다",
        }
        result = collector.collect(event)
        assert result is True  # 수집됨 (v2: 스킵하지 않음)

    def test_collect_non_mention_thread(self, store, tracker):
        """멘션과 무관한 스레드 메시지는 정상 수집"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=tracker,
        )
        # 다른 스레드만 마킹
        tracker.mark("9999.0000")

        event = {
            "channel": "C_OBS",
            "ts": "1234.9999",
            "user": "U001",
            "text": "일반 스레드 메시지",
            "thread_ts": "1234.0000",
        }
        result = collector.collect(event)
        assert result is True

    def test_auto_detect_bot_mention_and_collect(self, store, tracker):
        """봇 멘션이 포함된 메시지를 자동 감지하여 마킹 + 수집"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=tracker,
            bot_user_id="BOT123",
        )

        # 봇 멘션이 포함된 채널 루트 메시지
        event = {
            "channel": "C_OBS",
            "ts": "1234.5678",
            "user": "U001",
            "text": "<@BOT123> 안녕하세요",
        }
        result = collector.collect(event)
        # 자동 감지 후 마킹 + 수집
        assert result is True  # v2: 수집됨
        assert tracker.is_handled("1234.5678") is True  # 마킹도 됨

    def test_auto_detect_bot_mention_in_thread(self, store, tracker):
        """스레드 내 봇 멘션도 자동 감지하여 thread_ts를 마킹 + 수집"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=tracker,
            bot_user_id="BOT123",
        )

        event = {
            "channel": "C_OBS",
            "ts": "1234.9999",
            "user": "U001",
            "text": "<@BOT123> 스레드에서 멘션",
            "thread_ts": "1234.0000",
        }
        result = collector.collect(event)
        assert result is True  # v2: 수집됨
        # thread_ts가 마킹됨
        assert tracker.is_handled("1234.0000") is True

    def test_no_tracker_collects_normally(self, store):
        """mention_tracker가 없으면 기존과 동일하게 수집"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=None,
        )
        event = {
            "channel": "C_OBS",
            "ts": "1234.5678",
            "user": "U001",
            "text": "일반 메시지",
        }
        result = collector.collect(event)
        assert result is True

    def test_other_user_mention_not_filtered(self, store, tracker):
        """다른 사용자 멘션은 필터링하지 않음"""
        collector = ChannelMessageCollector(
            store=store,
            target_channels=["C_OBS"],
            mention_tracker=tracker,
            bot_user_id="BOT123",
        )
        event = {
            "channel": "C_OBS",
            "ts": "1234.5678",
            "user": "U001",
            "text": "<@OTHER_USER> 안녕",
        }
        result = collector.collect(event)
        assert result is True
        assert tracker.is_handled("1234.5678") is False


# ── Pipeline + MentionTracker 통합 테스트 ──────────────

class TestPipelineWithMentionTracker:
    """파이프라인에서 멘션 스레드가 소화(consume)되지만 리액션은 필터링되는지 테스트

    v2 변경:
    - 멘션 스레드 메시지는 judge에서 제외 (토큰 절약)
    - 멘션 스레드 메시지는 pending→judged로 정상 이동 (소화)
    - 멘션 스레드에 대한 리액션/개입은 필터링
    """

    @pytest.mark.asyncio
    async def test_mention_thread_excluded_from_judge(self, store, tracker, tmp_path):
        """멘션으로 처리 중인 스레드 메시지가 judge에서 제외됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # pending에 일반 메시지와 멘션 스레드 메시지를 섞어 넣음
        store.append_pending(channel_id, {
            "ts": "1001.000", "user": "U1", "text": "일반 메시지 " * 20,
        })
        store.append_pending(channel_id, {
            "ts": "1002.000", "user": "U2", "text": "멘션 스레드 메시지 " * 20,
            "thread_ts": "MENTION_THREAD",
        })
        store.append_pending(channel_id, {
            "ts": "1003.000", "user": "U3", "text": "또 다른 일반 메시지 " * 20,
        })

        # 멘션 스레드 마킹
        tracker.mark("MENTION_THREAD")

        # FakeObserver
        class FakeObs:
            judge_count = 0
            last_pending = []

            async def judge(self, **kwargs):
                FakeObs.judge_count += 1
                FakeObs.last_pending = kwargs.get("pending_messages", [])
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # judge에 전달된 pending에서 멘션 스레드 메시지가 제외됨
        assert observer.judge_count == 1
        pending_ts = {m["ts"] for m in observer.last_pending}
        assert "1001.000" in pending_ts
        assert "1003.000" in pending_ts
        assert "1002.000" not in pending_ts  # 멘션 스레드 메시지 제외

    @pytest.mark.asyncio
    async def test_mention_thread_consumed_to_judged(self, store, tracker, tmp_path):
        """멘션 스레드 메시지가 pending에서 judged로 정상 이동(소화)됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # pending에 일반 메시지와 멘션 스레드 메시지
        store.append_pending(channel_id, {
            "ts": "1001.000", "user": "U1", "text": "일반 메시지 " * 20,
        })
        store.append_pending(channel_id, {
            "ts": "1002.000", "user": "U2", "text": "멘션 스레드 메시지 " * 20,
            "thread_ts": "MENTION_THREAD",
        })

        tracker.mark("MENTION_THREAD")

        class FakeObs:
            async def judge(self, **kwargs):
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # pending이 비워져야 함 (멘션 포함 모두 judged로 이동)
        remaining_pending = store.load_pending(channel_id)
        assert len(remaining_pending) == 0

        # judged에 모든 메시지가 있어야 함
        judged = store.load_judged(channel_id)
        judged_ts = {m["ts"] for m in judged}
        assert "1001.000" in judged_ts
        assert "1002.000" in judged_ts  # 멘션 스레드도 소화됨

    @pytest.mark.asyncio
    async def test_mention_thread_buffers_excluded_from_judge(self, store, tracker, tmp_path):
        """멘션으로 처리 중인 스레드가 judge의 thread_buffers에서 제외됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # pending에 일반 메시지
        store.append_pending(channel_id, {
            "ts": "1001.000", "user": "U1", "text": "일반 메시지 " * 20,
        })
        # thread buffer에 멘션 스레드와 일반 스레드
        store.append_thread_message(channel_id, "MENTION_THREAD", {
            "ts": "2001.000", "user": "U2", "text": "멘션 스레드 대화",
        })
        store.append_thread_message(channel_id, "NORMAL_THREAD", {
            "ts": "3001.000", "user": "U3", "text": "일반 스레드 대화",
        })

        tracker.mark("MENTION_THREAD")

        class FakeObs:
            last_thread_buffers = None

            async def judge(self, **kwargs):
                FakeObs.last_thread_buffers = kwargs.get("thread_buffers")
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # judge에서 MENTION_THREAD가 제외됨
        assert "MENTION_THREAD" not in observer.last_thread_buffers
        assert "NORMAL_THREAD" in observer.last_thread_buffers

    @pytest.mark.asyncio
    async def test_mention_thread_buffers_consumed(self, store, tracker, tmp_path):
        """멘션 스레드의 thread_buffer도 정상 소화(consume)됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        store.append_pending(channel_id, {
            "ts": "1001.000", "user": "U1", "text": "일반 메시지 " * 20,
        })
        store.append_thread_message(channel_id, "MENTION_THREAD", {
            "ts": "2001.000", "user": "U2", "text": "멘션 스레드 대화",
        })

        tracker.mark("MENTION_THREAD")

        class FakeObs:
            async def judge(self, **kwargs):
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # pending이 비워져야 함
        assert len(store.load_pending(channel_id)) == 0

        # thread buffer도 비워져야 함 (judged로 이동)
        assert len(store.load_all_thread_buffers(channel_id)) == 0

        # judged에 모든 메시지가 있어야 함
        judged = store.load_judged(channel_id)
        judged_ts = {m["ts"] for m in judged}
        assert "1001.000" in judged_ts
        assert "2001.000" in judged_ts

    @pytest.mark.asyncio
    async def test_mention_thread_no_reaction(self, store, tracker, tmp_path):
        """멘션 스레드에 대해 리액션/개입이 발생하지 않음"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # 멘션 스레드에 속한 메시지
        store.append_pending(channel_id, {
            "ts": "MENTION_MSG", "user": "U1", "text": "멘션 메시지 " * 20,
            "thread_ts": "MENTION_THREAD",
        })
        # 일반 메시지
        store.append_pending(channel_id, {
            "ts": "NORMAL_MSG", "user": "U2", "text": "일반 메시지 " * 20,
        })

        tracker.mark("MENTION_THREAD")

        class FakeObs:
            async def judge(self, **kwargs):
                # 일반 메시지에만 react 반응
                return JudgeResult(items=[
                    JudgeItem(
                        ts="NORMAL_MSG",
                        importance=5,
                        reaction_type="react",
                        reaction_target="NORMAL_MSG",
                        reaction_content="thumbsup",
                    ),
                ])

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        # reactions_add 호출 추적
        client.reactions_add = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # 일반 메시지에는 리액션이 실행됨
        client.reactions_add.assert_called_once()
        call_kwargs = client.reactions_add.call_args.kwargs
        assert call_kwargs.get("name") == "thumbsup"
        assert call_kwargs.get("timestamp") == "NORMAL_MSG"

    @pytest.mark.asyncio
    async def test_mention_thread_no_intervention(self, store, tracker, tmp_path):
        """멘션 스레드에 대한 intervene 액션도 필터링됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # 멘션 스레드에 속한 메시지
        store.append_pending(channel_id, {
            "ts": "MENTION_MSG", "user": "U1", "text": "멘션 메시지 " * 20,
            "thread_ts": "MENTION_THREAD",
        })
        # 일반 메시지
        store.append_pending(channel_id, {
            "ts": "NORMAL_MSG", "user": "U2", "text": "일반 메시지 " * 20,
        })

        tracker.mark("MENTION_THREAD")

        class FakeObs:
            async def judge(self, **kwargs):
                # 일반 메시지에 intervene 반응 (멘션 메시지는 judge에 전달 안 됨)
                return JudgeResult(items=[
                    JudgeItem(
                        ts="NORMAL_MSG",
                        importance=8,
                        reaction_type="intervene",
                        reaction_target="NORMAL_MSG",
                        reaction_content="이건 중요한 메시지입니다",
                    ),
                ])

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        client.reactions_add = MagicMock()
        client.reactions_remove = MagicMock()
        client.chat_postMessage = MagicMock(return_value={"ts": "resp.000"})
        history = InterventionHistory(base_dir=tmp_path)

        # llm_call을 제공하지 않으면 execute_interventions 경로로 감
        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
            intervention_threshold=0.0,  # 항상 개입 통과
        )

        # pending이 모두 소화됨 (멘션 포함)
        assert len(store.load_pending(channel_id)) == 0
        judged = store.load_judged(channel_id)
        judged_ts = {m["ts"] for m in judged}
        assert "MENTION_MSG" in judged_ts
        assert "NORMAL_MSG" in judged_ts

    @pytest.mark.asyncio
    async def test_no_mention_tracker_backward_compatible(self, store, tmp_path):
        """mention_tracker 없이도 기존과 동일하게 동작"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        store.append_pending(channel_id, {
            "ts": "1001.000", "user": "U1", "text": "일반 메시지 " * 20,
        })

        class FakeObs:
            judge_count = 0

            async def judge(self, **kwargs):
                FakeObs.judge_count += 1
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            # mention_tracker 미전달
        )

        assert observer.judge_count == 1

    @pytest.mark.asyncio
    async def test_mention_root_message_excluded_from_judge(self, store, tracker, tmp_path):
        """멘션 루트 메시지 자체도 judge에서 제외됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # 멘션 루트 메시지 (thread_ts 없음, ts가 마킹됨)
        store.append_pending(channel_id, {
            "ts": "MENTION_ROOT", "user": "U1",
            "text": "<@BOT123> 질문입니다 " * 20,
        })
        store.append_pending(channel_id, {
            "ts": "1002.000", "user": "U2", "text": "일반 메시지 " * 20,
        })

        tracker.mark("MENTION_ROOT")

        class FakeObs:
            last_pending = []

            async def judge(self, **kwargs):
                FakeObs.last_pending = kwargs.get("pending_messages", [])
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        pending_ts = {m["ts"] for m in observer.last_pending}
        assert "MENTION_ROOT" not in pending_ts
        assert "1002.000" in pending_ts

    @pytest.mark.asyncio
    async def test_mention_root_consumed_to_judged(self, store, tracker, tmp_path):
        """멘션 루트 메시지도 pending→judged로 소화됨"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        store.append_pending(channel_id, {
            "ts": "MENTION_ROOT", "user": "U1",
            "text": "<@BOT123> 질문입니다 " * 20,
        })

        tracker.mark("MENTION_ROOT")

        class FakeObs:
            async def judge(self, **kwargs):
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # pending이 비워져야 함
        assert len(store.load_pending(channel_id)) == 0
        # judged에 소화됨
        judged = store.load_judged(channel_id)
        judged_ts = {m["ts"] for m in judged}
        assert "MENTION_ROOT" in judged_ts

    @pytest.mark.asyncio
    async def test_non_mention_channel_mention_unaffected(self, store, tracker, tmp_path):
        """모니터 대상이 아닌 채널의 멘션은 관찰자 동작에 영향 없음"""
        from seosoyoung.slackbot.memory.channel_pipeline import run_channel_pipeline

        channel_id = "C_TEST"
        # 이 채널의 pending은 멘션과 무관
        store.append_pending(channel_id, {
            "ts": "1001.000", "user": "U1", "text": "일반 메시지 " * 20,
        })

        # 다른 채널의 멘션 스레드를 마킹 (이 채널에 영향 없어야 함)
        tracker.mark("OTHER_CHANNEL_THREAD")

        class FakeObs:
            last_pending = []

            async def judge(self, **kwargs):
                FakeObs.last_pending = kwargs.get("pending_messages", [])
                return JudgeResult(importance=3, reaction_type="none")

            async def digest(self, **kwargs):
                return None

        observer = FakeObs()
        client = MagicMock()
        history = InterventionHistory(base_dir=tmp_path)

        await run_channel_pipeline(
            store=store,
            observer=observer,
            channel_id=channel_id,
            slack_client=client,
            cooldown=history,
            threshold_a=1,
            mention_tracker=tracker,
        )

        # 이 채널의 메시지는 필터링되지 않음
        assert len(observer.last_pending) == 1
        assert observer.last_pending[0]["ts"] == "1001.000"
