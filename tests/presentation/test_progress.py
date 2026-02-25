"""build_progress_callbacks 유닛 테스트

PresentationContext를 캡처하는 on_progress/on_compact 콜백 쌍의
동작을 검증합니다.
"""

import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.presentation.progress import build_progress_callbacks, _STALE_CHECK_INTERVAL


def _make_pctx(**overrides) -> PresentationContext:
    """테스트용 PresentationContext 생성"""
    client = MagicMock()
    # conversations_replies 기본 반환값: 메시지 없음 (stale 아님)
    client.conversations_replies.return_value = {"messages": []}
    defaults = {
        "channel": "C123",
        "thread_ts": "1234.5678",
        "msg_ts": "1234.9999",
        "say": MagicMock(),
        "client": client,
        "effective_role": "admin",
        "session_id": "sess-001",
        "last_msg_ts": "1234.6000",
        # stale 체크를 기본적으로 스킵하도록 최근 시각으로 설정
        "_last_stale_check": time.monotonic(),
    }
    defaults.update(overrides)
    return PresentationContext(**defaults)


class TestBuildProgressCallbacks:
    """build_progress_callbacks 팩토리 함수 테스트"""

    def test_returns_two_callables(self):
        """on_progress, on_compact 두 콜백을 반환한다"""
        pctx = _make_pctx()
        update_fn = MagicMock()

        on_progress, on_compact = build_progress_callbacks(pctx, update_fn)

        assert callable(on_progress)
        assert callable(on_compact)

    @pytest.mark.asyncio
    async def test_normal_mode_progress_calls_update_message(self):
        """일반 모드에서 on_progress가 update_message_fn을 호출한다"""
        pctx = _make_pctx()
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("Hello world")

        update_fn.assert_called_once()
        args = update_fn.call_args
        assert args[0][0] is pctx.client   # client
        assert args[0][1] == "C123"         # channel
        assert args[0][2] == "1234.6000"    # last_msg_ts

    @pytest.mark.asyncio
    async def test_normal_mode_progress_empty_text_skipped(self):
        """빈 텍스트는 무시된다"""
        pctx = _make_pctx()
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("")

        update_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_trello_mode_with_dm(self):
        """트렐로 모드 + DM 설정 시 DM 채널에 메시지 전송"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "dm_reply_1"}

        pctx = _make_pctx(
            client=client,
            is_trello_mode=True,
            trello_card=MagicMock(card_name="Test Card"),
            dm_channel_id="D999",
            dm_thread_ts="dm_thread_1",
        )
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("작업 진행 중입니다")

        # DM 채널에 chat_postMessage 호출
        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "D999"
        assert call_kwargs["thread_ts"] == "dm_thread_1"

        # pctx.dm_last_reply_ts가 갱신됨
        assert pctx.dm_last_reply_ts == "dm_reply_1"

        # update_message_fn은 호출되지 않음
        update_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_trello_mode_without_dm(self):
        """트렐로 모드 + DM 없음 → 메인 메시지 업데이트"""
        pctx = _make_pctx(
            is_trello_mode=True,
            trello_card=MagicMock(card_name="Test Card"),
            main_msg_ts="main_1",
        )
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("작업 진행 중입니다")

        update_fn.assert_called_once()
        args = update_fn.call_args
        assert args[0][2] == "main_1"  # main_msg_ts 사용

    @pytest.mark.asyncio
    async def test_on_compact_auto_trigger(self):
        """on_compact auto 트리거 시 chat_postMessage로 자동 압축 알림"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_ts_1"}
        pctx = _make_pctx(client=client)
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        await on_compact("auto", "context compacted")

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert call_kwargs["thread_ts"] == "1234.5678"
        assert "자동 압축" in call_kwargs["text"]
        # compact_msg_ts가 저장됨
        assert pctx.compact_msg_ts == "compact_ts_1"

    @pytest.mark.asyncio
    async def test_on_compact_manual_trigger(self):
        """on_compact manual 트리거 시 chat_postMessage로 수동 압축 알림"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_ts_2"}
        pctx = _make_pctx(client=client)
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        await on_compact("manual", "user requested compact")

        client.chat_postMessage.assert_called_once()
        call_kwargs = client.chat_postMessage.call_args[1]
        assert "압축" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_progress_error_handled_gracefully(self):
        """on_progress 에러가 예외를 전파하지 않는다"""
        pctx = _make_pctx()
        update_fn = MagicMock(side_effect=Exception("Slack API error"))

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        # 예외가 전파되지 않아야 함 (chat_postMessage 폴백도 실패할 수 있음)
        pctx.client.chat_postMessage.side_effect = Exception("also failed")
        await on_progress("Hello")

    @pytest.mark.asyncio
    async def test_compact_error_handled_gracefully(self):
        """on_compact 에러가 예외를 전파하지 않는다"""
        client = MagicMock()
        client.chat_postMessage.side_effect = Exception("Slack API error")
        pctx = _make_pctx(client=client)
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        # 예외가 전파되지 않아야 함
        await on_compact("auto", "message")


class TestPresentationContextMutation:
    """PresentationContext의 mutable 필드 갱신 검증"""

    @pytest.mark.asyncio
    async def test_dm_last_reply_ts_updated_by_progress(self):
        """on_progress가 dm_last_reply_ts를 갱신한다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "new_reply_ts"}

        pctx = _make_pctx(
            client=client,
            is_trello_mode=True,
            dm_channel_id="D999",
            dm_thread_ts="dm_thread_1",
        )

        assert pctx.dm_last_reply_ts is None

        on_progress, _ = build_progress_callbacks(pctx, MagicMock())
        await on_progress("test")

        assert pctx.dm_last_reply_ts == "new_reply_ts"

    def test_pctx_fields_accessible(self):
        """PresentationContext 필드가 올바르게 접근 가능하다"""
        pctx = _make_pctx(
            user_id="U999",
            trello_card=MagicMock(card_id="card-1"),
            is_trello_mode=True,
        )

        assert pctx.channel == "C123"
        assert pctx.thread_ts == "1234.5678"
        assert pctx.user_id == "U999"
        assert pctx.is_trello_mode is True
        assert pctx.trello_card.card_id == "card-1"


class TestCompactCompletion:
    """변경 2: 오토 컴팩트 완료 메시지 테스트"""

    @pytest.mark.asyncio
    async def test_compact_stores_ts(self):
        """on_compact가 전송한 메시지의 ts를 compact_msg_ts에 저장한다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_msg_001"}
        pctx = _make_pctx(client=client)
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        assert pctx.compact_msg_ts is None
        await on_compact("auto", "compacting")
        assert pctx.compact_msg_ts == "compact_msg_001"

    @pytest.mark.asyncio
    async def test_compact_updates_previous_compact_message(self):
        """두 번째 compact 호출 시 이전 compact 메시지를 완료로 갱신한다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_msg_002"}
        pctx = _make_pctx(client=client, compact_msg_ts="compact_msg_001")
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        await on_compact("auto", "compacting again")

        # chat_update로 이전 메시지 갱신
        client.chat_update.assert_called_once()
        update_kwargs = client.chat_update.call_args[1]
        assert update_kwargs["ts"] == "compact_msg_001"
        assert "완료" in update_kwargs["text"]

        # 새 메시지 ts 저장
        assert pctx.compact_msg_ts == "compact_msg_002"

    @pytest.mark.asyncio
    async def test_progress_clears_compact_msg_ts(self):
        """on_progress 호출 시 compact_msg_ts가 있으면 완료 갱신 후 None으로 초기화"""
        client = MagicMock()
        pctx = _make_pctx(client=client, compact_msg_ts="compact_msg_001")
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("사고 중...")

        # chat_update로 compact 메시지 완료 갱신
        client.chat_update.assert_called_once()
        update_kwargs = client.chat_update.call_args[1]
        assert update_kwargs["ts"] == "compact_msg_001"
        assert "완료" in update_kwargs["text"]

        # compact_msg_ts 초기화
        assert pctx.compact_msg_ts is None

    @pytest.mark.asyncio
    async def test_compact_update_failure_does_not_block(self):
        """compact 완료 갱신 실패 시 다음 처리가 계속 진행된다"""
        client = MagicMock()
        client.chat_update.side_effect = Exception("update failed")
        client.chat_postMessage.return_value = {"ts": "new_compact_ts"}
        pctx = _make_pctx(client=client, compact_msg_ts="old_ts")
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        # 예외가 전파되지 않고 새 메시지가 전송되어야 함
        await on_compact("auto", "compacting")
        assert pctx.compact_msg_ts == "new_compact_ts"

    @pytest.mark.asyncio
    async def test_compact_resets_stale_check(self):
        """on_compact 호출 후 _last_stale_check가 0.0으로 리셋된다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "ts_123"}
        pctx = _make_pctx(client=client, _last_stale_check=time.monotonic())
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        await on_compact("auto", "compacting")

        assert pctx._last_stale_check == 0.0


class TestStaleThinkingRecovery:
    """변경 3: 사고 과정 갱신 모드 리커버리 테스트"""

    @pytest.mark.asyncio
    async def test_stale_detected_posts_new_message(self):
        """stale 감지 시 새 메시지를 전송하고 last_msg_ts를 교체한다"""
        client = MagicMock()
        # conversations_replies: 새 메시지 있음 → stale
        client.conversations_replies.return_value = {"messages": [{"ts": "newer_msg"}]}
        client.chat_postMessage.return_value = {"ts": "new_thinking_ts"}

        pctx = _make_pctx(
            client=client,
            last_msg_ts="old_thinking_ts",
            _last_stale_check=0.0,  # 즉시 체크 가능
        )
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("사고 중...")

        # conversations_replies 호출됨
        client.conversations_replies.assert_called_once()
        call_kwargs = client.conversations_replies.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert call_kwargs["ts"] == "1234.5678"
        assert call_kwargs["oldest"] == "old_thinking_ts"
        assert call_kwargs["inclusive"] is False

        # 새 메시지 전송
        client.chat_postMessage.assert_called_once()
        assert pctx.last_msg_ts == "new_thinking_ts"

        # update_message_fn은 호출되지 않음 (새 메시지를 보냈으므로)
        update_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_check_rate_limited(self):
        """마지막 stale 체크로부터 10초 미만이면 체크를 스킵한다"""
        client = MagicMock()
        pctx = _make_pctx(
            client=client,
            _last_stale_check=time.monotonic(),  # 방금 체크함
        )
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("사고 중...")

        # conversations_replies는 호출되지 않음
        client.conversations_replies.assert_not_called()
        # update_message_fn은 정상 호출됨
        update_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_stale_without_new_messages(self):
        """새 메시지가 없으면 stale 아님 → 일반 update_message_fn 호출"""
        client = MagicMock()
        # conversations_replies: 새 메시지 없음
        client.conversations_replies.return_value = {"messages": []}

        pctx = _make_pctx(
            client=client,
            _last_stale_check=0.0,  # 즉시 체크
        )
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("사고 중...")

        # conversations_replies 호출됨
        client.conversations_replies.assert_called_once()
        # stale 아니므로 update_message_fn 호출
        update_fn.assert_called_once()
        # last_msg_ts 변경 없음
        assert pctx.last_msg_ts == "1234.6000"

    @pytest.mark.asyncio
    async def test_compact_resets_stale_check_for_immediate_next_check(self):
        """on_compact 호출 후 즉시 stale 체크가 가능해진다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "compact_ts"}
        pctx = _make_pctx(client=client, _last_stale_check=time.monotonic())
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        # compact 전에는 stale 체크 rate-limited
        assert time.monotonic() - pctx._last_stale_check < _STALE_CHECK_INTERVAL

        await on_compact("auto", "compacting")

        # compact 후에는 즉시 체크 가능
        assert pctx._last_stale_check == 0.0

    @pytest.mark.asyncio
    async def test_update_message_failure_falls_back_to_post_message(self):
        """update_message_fn 실패 시 chat_postMessage로 폴백한다"""
        from slack_sdk.errors import SlackApiError

        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "fallback_ts"}
        pctx = _make_pctx(client=client)
        # update_message_fn 실패
        update_fn = MagicMock(side_effect=Exception("message not found"))

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("사고 중...")

        # chat_postMessage 폴백 호출
        client.chat_postMessage.assert_called_once()
        # last_msg_ts 갱신
        assert pctx.last_msg_ts == "fallback_ts"

    @pytest.mark.asyncio
    async def test_trello_mode_skips_stale_check(self):
        """트렐로 모드에서는 stale 체크를 수행하지 않는다"""
        client = MagicMock()
        client.chat_postMessage.return_value = {"ts": "dm_ts"}
        pctx = _make_pctx(
            client=client,
            is_trello_mode=True,
            dm_channel_id="D999",
            dm_thread_ts="dm_thread_1",
            _last_stale_check=0.0,
        )
        update_fn = MagicMock()

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        await on_progress("작업 중...")

        # 트렐로 모드에서는 conversations_replies 호출 안 됨
        client.conversations_replies.assert_not_called()
