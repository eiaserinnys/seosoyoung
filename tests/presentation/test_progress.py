"""build_progress_callbacks 유닛 테스트

PresentationContext를 캡처하는 on_progress/on_compact 콜백 쌍의
동작을 검증합니다.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from seosoyoung.slackbot.presentation.types import PresentationContext
from seosoyoung.slackbot.presentation.progress import build_progress_callbacks


def _make_pctx(**overrides) -> PresentationContext:
    """테스트용 PresentationContext 생성"""
    defaults = {
        "channel": "C123",
        "thread_ts": "1234.5678",
        "msg_ts": "1234.9999",
        "say": MagicMock(),
        "client": MagicMock(),
        "effective_role": "admin",
        "session_id": "sess-001",
        "last_msg_ts": "1234.6000",
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
        """on_compact auto 트리거 시 자동 압축 알림"""
        pctx = _make_pctx()
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        await on_compact("auto", "context compacted")

        pctx.say.assert_called_once()
        call_kwargs = pctx.say.call_args[1]
        assert call_kwargs["thread_ts"] == "1234.5678"
        assert "자동 압축" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_on_compact_manual_trigger(self):
        """on_compact manual 트리거 시 수동 압축 알림"""
        pctx = _make_pctx()
        update_fn = MagicMock()

        _, on_compact = build_progress_callbacks(pctx, update_fn)

        await on_compact("manual", "user requested compact")

        pctx.say.assert_called_once()
        call_kwargs = pctx.say.call_args[1]
        assert "압축" in call_kwargs["text"]

    @pytest.mark.asyncio
    async def test_progress_error_handled_gracefully(self):
        """on_progress 에러가 예외를 전파하지 않는다"""
        pctx = _make_pctx()
        update_fn = MagicMock(side_effect=Exception("Slack API error"))

        on_progress, _ = build_progress_callbacks(pctx, update_fn)

        # 예외가 전파되지 않아야 함
        await on_progress("Hello")

    @pytest.mark.asyncio
    async def test_compact_error_handled_gracefully(self):
        """on_compact 에러가 예외를 전파하지 않는다"""
        pctx = _make_pctx()
        pctx.say = MagicMock(side_effect=Exception("Slack API error"))
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
