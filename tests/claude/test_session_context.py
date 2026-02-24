"""세션 컨텍스트 주입 테스트"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from seosoyoung.claude.session_context import (
    build_initial_context,
    build_followup_context,
    format_hybrid_context,
)


class TestBuildInitialContext:
    """세션 최초 생성 시 채널 컨텍스트 구성 테스트"""

    def _make_msg(self, ts, user="U001", text="hello"):
        return {"ts": ts, "user": user, "text": text}

    def test_basic_channel_history_only(self):
        """모니터링 채널이 아닌 경우 슬랙 히스토리만 반환"""
        slack_messages = [
            self._make_msg("1.0", text="msg1"),
            self._make_msg("2.0", text="msg2"),
            self._make_msg("3.0", text="msg3"),
        ]

        result = build_initial_context(
            channel_id="C_NOT_MONITORED",
            slack_messages=slack_messages,
            monitored_channels=[],
            channel_store=None,
        )

        assert len(result["messages"]) == 3
        assert result["last_seen_ts"] == "3.0"
        assert result["source_type"] == "thread"

    def test_limits_to_7_messages(self):
        """최대 7개 메시지로 제한"""
        slack_messages = [self._make_msg(f"{i}.0") for i in range(1, 15)]

        result = build_initial_context(
            channel_id="C001",
            slack_messages=slack_messages,
            monitored_channels=[],
            channel_store=None,
        )

        assert len(result["messages"]) == 7
        # 가장 최근 7개만 포함 (ts 8~14)
        assert result["messages"][0]["ts"] == "8.0"
        assert result["messages"][-1]["ts"] == "14.0"
        assert result["last_seen_ts"] == "14.0"

    def test_monitored_channel_includes_judged(self):
        """모니터링 채널이면 judged 메시지도 포함"""
        slack_messages = [
            self._make_msg("5.0", text="slack_msg"),
        ]

        store = MagicMock()
        store.load_judged.return_value = [
            self._make_msg("1.0", text="judged1"),
            self._make_msg("2.0", text="judged2"),
        ]
        store.load_pending.return_value = [
            self._make_msg("3.0", text="pending1"),
        ]

        result = build_initial_context(
            channel_id="C_MON",
            slack_messages=slack_messages,
            monitored_channels=["C_MON"],
            channel_store=store,
        )

        # judged(2) + pending(1) + slack(1) = 4, 중복 제거 후 시간순
        assert result["source_type"] == "hybrid"
        texts = [m["text"] for m in result["messages"]]
        assert "judged1" in texts
        assert "pending1" in texts
        assert "slack_msg" in texts

    def test_monitored_channel_deduplicates_by_ts(self):
        """ts가 같은 메시지는 중복 제거"""
        slack_messages = [
            self._make_msg("1.0", text="from_slack"),
            self._make_msg("2.0", text="from_slack_2"),
        ]

        store = MagicMock()
        store.load_judged.return_value = [
            self._make_msg("1.0", text="from_judged"),  # ts 중복
        ]
        store.load_pending.return_value = []

        result = build_initial_context(
            channel_id="C_MON",
            slack_messages=slack_messages,
            monitored_channels=["C_MON"],
            channel_store=store,
        )

        ts_list = [m["ts"] for m in result["messages"]]
        assert ts_list.count("1.0") == 1

    def test_monitored_channel_limit_7(self):
        """모니터링 채널에서도 최대 7개"""
        slack_messages = [self._make_msg(f"{i}.0") for i in range(1, 6)]

        store = MagicMock()
        store.load_judged.return_value = [
            self._make_msg(f"{i}.0") for i in range(10, 16)
        ]
        store.load_pending.return_value = [
            self._make_msg("20.0"),
        ]

        result = build_initial_context(
            channel_id="C_MON",
            slack_messages=slack_messages,
            monitored_channels=["C_MON"],
            channel_store=store,
        )

        assert len(result["messages"]) == 7
        assert result["last_seen_ts"] == "20.0"

    def test_empty_messages(self):
        """메시지가 없는 경우"""
        result = build_initial_context(
            channel_id="C001",
            slack_messages=[],
            monitored_channels=[],
            channel_store=None,
        )

        assert result["messages"] == []
        assert result["last_seen_ts"] == ""
        assert result["source_type"] == "thread"

    def test_time_sorted(self):
        """메시지가 시간순으로 정렬"""
        slack_messages = [
            self._make_msg("3.0"),
            self._make_msg("1.0"),
            self._make_msg("5.0"),
        ]

        result = build_initial_context(
            channel_id="C001",
            slack_messages=slack_messages,
            monitored_channels=[],
            channel_store=None,
        )

        ts_list = [m["ts"] for m in result["messages"]]
        assert ts_list == ["1.0", "3.0", "5.0"]


class TestBuildFollowupContext:
    """후속 요청 시 증분 컨텍스트 구성 테스트"""

    def _make_msg(self, ts, user="U001", text="hello", linked_message_ts=None):
        msg = {"ts": ts, "user": user, "text": text}
        if linked_message_ts:
            msg["linked_message_ts"] = linked_message_ts
        return msg

    def test_non_monitored_returns_empty(self):
        """모니터링 채널이 아닌 경우 빈 결과 반환"""
        result = build_followup_context(
            channel_id="C_NOT_MON",
            last_seen_ts="5.0",
            channel_store=None,
            monitored_channels=[],
        )

        assert result["messages"] == []
        assert result["last_seen_ts"] == "5.0"

    def test_unseen_messages_after_last_seen(self):
        """last_seen_ts 이후 메시지만 반환"""
        store = MagicMock()
        store.load_judged.return_value = [
            self._make_msg("1.0", text="old"),
            self._make_msg("3.0", text="old2"),
        ]
        store.load_pending.return_value = [
            self._make_msg("6.0", text="new1"),
            self._make_msg("8.0", text="new2"),
        ]

        result = build_followup_context(
            channel_id="C_MON",
            last_seen_ts="5.0",
            channel_store=store,
            monitored_channels=["C_MON"],
        )

        assert len(result["messages"]) == 2
        assert result["messages"][0]["text"] == "new1"
        assert result["messages"][1]["text"] == "new2"
        assert result["last_seen_ts"] == "8.0"

    def test_no_new_messages(self):
        """새 메시지가 없는 경우"""
        store = MagicMock()
        store.load_judged.return_value = [
            self._make_msg("1.0"),
        ]
        store.load_pending.return_value = []

        result = build_followup_context(
            channel_id="C_MON",
            last_seen_ts="5.0",
            channel_store=store,
            monitored_channels=["C_MON"],
        )

        assert result["messages"] == []
        assert result["last_seen_ts"] == "5.0"

    def test_linked_chain_included(self):
        """linked_message_ts가 가리키는 이전 메시지도 포함"""
        store = MagicMock()
        store.load_judged.return_value = [
            self._make_msg("2.0", text="referenced_msg"),
            self._make_msg("3.0", text="old_msg"),
        ]
        store.load_pending.return_value = [
            self._make_msg("6.0", text="new_links_back", linked_message_ts="2.0"),
        ]

        result = build_followup_context(
            channel_id="C_MON",
            last_seen_ts="5.0",
            channel_store=store,
            monitored_channels=["C_MON"],
        )

        # "2.0"은 last_seen_ts 이전이지만 linked로 포함
        ts_list = [m["ts"] for m in result["messages"]]
        assert "2.0" in ts_list
        assert "6.0" in ts_list
        # "3.0"은 참조되지 않으므로 미포함
        assert "3.0" not in ts_list

    def test_linked_after_cutoff_not_duplicated(self):
        """linked_message_ts가 cutoff 이후면 이미 unseen에 있으므로 중복 안됨"""
        store = MagicMock()
        store.load_judged.return_value = []
        store.load_pending.return_value = [
            self._make_msg("6.0", text="msg_a"),
            self._make_msg("8.0", text="msg_b", linked_message_ts="6.0"),
        ]

        result = build_followup_context(
            channel_id="C_MON",
            last_seen_ts="5.0",
            channel_store=store,
            monitored_channels=["C_MON"],
        )

        ts_list = [m["ts"] for m in result["messages"]]
        assert ts_list.count("6.0") == 1
        assert len(result["messages"]) == 2

    def test_empty_last_seen_ts(self):
        """last_seen_ts가 비어있으면 빈 결과"""
        store = MagicMock()

        result = build_followup_context(
            channel_id="C_MON",
            last_seen_ts="",
            channel_store=store,
            monitored_channels=["C_MON"],
        )

        assert result["messages"] == []

    def test_limit_10_messages(self):
        """최대 10개 제한"""
        store = MagicMock()
        store.load_judged.return_value = []
        store.load_pending.return_value = [
            self._make_msg(f"{i}.0") for i in range(10, 25)
        ]

        result = build_followup_context(
            channel_id="C_MON",
            last_seen_ts="5.0",
            channel_store=store,
            monitored_channels=["C_MON"],
        )

        assert len(result["messages"]) == 10


class TestFormatHybridContext:
    """hybrid 세션 프롬프트 포맷 테스트"""

    def _make_msg(self, ts, user="U001", text="hello", linked_message_ts=None):
        msg = {"ts": ts, "user": user, "text": text}
        if linked_message_ts:
            msg["linked_message_ts"] = linked_message_ts
        return msg

    def test_empty_messages(self):
        """메시지 없으면 빈 문자열"""
        assert format_hybrid_context([], "hybrid") == ""

    def test_hybrid_header(self):
        """hybrid 세션은 hybrid 헤더 포함"""
        messages = [self._make_msg("1.0", text="hi")]
        result = format_hybrid_context(messages, "hybrid")
        assert "hybrid 세션" in result
        assert "채널에서 수집" in result

    def test_thread_header(self):
        """thread 세션은 일반 헤더"""
        messages = [self._make_msg("1.0", text="hi")]
        result = format_hybrid_context(messages, "thread")
        assert "Slack 채널의 최근 대화" in result
        assert "hybrid" not in result

    def test_linked_info_included(self):
        """linked_message_ts가 있으면 [linked:ts] 표기"""
        messages = [
            self._make_msg("2.0", text="ref"),
            self._make_msg("5.0", text="new", linked_message_ts="2.0"),
        ]
        result = format_hybrid_context(messages, "hybrid")
        assert "[linked:2.0]" in result

    def test_message_format(self):
        """메시지가 <user>: text 형식"""
        messages = [self._make_msg("1.0", user="U123", text="hello world")]
        result = format_hybrid_context(messages, "hybrid")
        assert "<U123>: hello world" in result
