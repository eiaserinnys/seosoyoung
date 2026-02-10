"""Promoter / Compactor 모듈 + 파이프라인 연동 테스트"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.promoter import (
    Compactor,
    CompactorResult,
    Promoter,
    PromoterResult,
    _count_entries,
    _count_priority,
    _extract_tag,
    parse_compactor_output,
    parse_promoter_output,
)
from seosoyoung.memory.observation_pipeline import (
    _try_compact,
    _try_promote,
    observe_conversation,
)
from seosoyoung.memory.observer import ObserverResult
from seosoyoung.memory.store import MemoryStore
from seosoyoung.memory.token_counter import TokenCounter


@pytest.fixture
def store(tmp_path):
    return MemoryStore(base_dir=tmp_path)


@pytest.fixture
def mock_observer():
    observer = AsyncMock()
    observer.observe = AsyncMock()
    return observer


@pytest.fixture
def sample_messages():
    return [
        {"role": "user", "content": "캐릭터 정보를 수정해주세요. 펜릭스에 대해 설명을 추가하겠습니다."},
        {"role": "assistant", "content": "네, 펜릭스 캐릭터 설명을 추가하겠습니다. 어떤 내용을 추가할까요?"},
    ]


# ── parse helpers ────────────────────────────────────────────


class TestExtractTag:
    def test_extract_promoted(self):
        text = "<promoted>\n🔴 핵심 선호\n🟡 작업 패턴\n</promoted>"
        assert "핵심 선호" in _extract_tag(text, "promoted")

    def test_extract_rejected(self):
        text = "<rejected>\n- 일시적 맥락 (제거)\n</rejected>"
        assert "일시적 맥락" in _extract_tag(text, "rejected")

    def test_extract_compacted(self):
        text = "<compacted>\n🔴 압축된 기억\n</compacted>"
        assert "압축된 기억" in _extract_tag(text, "compacted")

    def test_extract_missing(self):
        assert _extract_tag("no tags here", "promoted") == ""

    def test_extract_empty_tag(self):
        text = "<promoted></promoted>"
        assert _extract_tag(text, "promoted") == ""


class TestCountEntries:
    def test_count_emoji_lines(self):
        text = "🔴 첫째\n🟡 둘째\n🟢 셋째"
        assert _count_entries(text) == 3

    def test_count_with_blank_lines(self):
        text = "🔴 첫째\n\n🟡 둘째"
        assert _count_entries(text) == 2

    def test_count_dash_lines(self):
        text = "- 항목 1\n- 항목 2"
        assert _count_entries(text) == 2

    def test_count_empty(self):
        assert _count_entries("") == 0
        assert _count_entries(None) == 0


class TestCountPriority:
    def test_priority_counts(self):
        text = "🔴 첫째\n🔴 둘째\n🟡 셋째\n🟢 넷째"
        counts = _count_priority(text)
        assert counts == {"🔴": 2, "🟡": 1, "🟢": 1}

    def test_empty(self):
        assert _count_priority("") == {}


class TestParsePromoterOutput:
    def test_parse_full(self):
        text = (
            "<promoted>\n🔴 한국어 커밋 선호\n🟡 체크리스트 패턴\n</promoted>\n"
            "<rejected>\n- 일시적 맥락 (세션 한정)\n- 단순 인사 (불필요)\n</rejected>"
        )
        result = parse_promoter_output(text)
        assert result.promoted_count == 2
        assert result.rejected_count == 2
        assert result.priority_counts == {"🔴": 1, "🟡": 1}
        assert "한국어 커밋 선호" in result.promoted

    def test_parse_no_promoted(self):
        text = "<promoted></promoted>\n<rejected>\n- 모두 기각\n</rejected>"
        result = parse_promoter_output(text)
        assert result.promoted_count == 0
        assert result.rejected_count == 1

    def test_parse_no_tags(self):
        text = "일반 텍스트"
        result = parse_promoter_output(text)
        assert result.promoted == ""
        assert result.rejected == ""


class TestParseCompactorOutput:
    def test_parse_compacted(self):
        text = "<compacted>\n🔴 압축된 핵심\n🟡 유지된 맥락\n</compacted>"
        result = parse_compactor_output(text)
        assert "압축된 핵심" in result

    def test_fallback_no_tag(self):
        text = "태그 없는 결과"
        assert parse_compactor_output(text) == "태그 없는 결과"


# ── Promoter class ───────────────────────────────────────────


class TestPromoterMerge:
    def test_merge_both(self):
        result = Promoter.merge_promoted("기존 기억", "새 기억")
        assert "기존 기억" in result
        assert "새 기억" in result

    def test_merge_no_existing(self):
        assert Promoter.merge_promoted("", "새 기억") == "새 기억"
        assert Promoter.merge_promoted(None, "새 기억") == "새 기억"

    def test_merge_no_promoted(self):
        assert Promoter.merge_promoted("기존 기억", "") == "기존 기억"
        assert Promoter.merge_promoted("기존 기억", None) == "기존 기억"


class TestPromoterFormatCandidates:
    def test_format(self):
        candidates = [
            {"ts": "2026-02-10T00:00:00", "priority": "🔴", "content": "핵심 선호"},
            {"ts": "2026-02-10T01:00:00", "priority": "🟡", "content": "작업 패턴"},
        ]
        text = Promoter._format_candidates(candidates)
        assert "🔴" in text
        assert "핵심 선호" in text
        assert "🟡" in text
        assert "작업 패턴" in text


class TestPromoterPromote:
    @pytest.mark.asyncio
    async def test_promote_calls_api(self):
        promoter = Promoter(api_key="test-key", model="test-model")
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="<promoted>\n🔴 승격 항목\n</promoted>\n<rejected>\n- 기각\n</rejected>"
                )
            )
        ]
        promoter.client = AsyncMock()
        promoter.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await promoter.promote(
            candidates=[{"ts": "t", "priority": "🔴", "content": "테스트"}],
            existing_persistent="기존",
        )

        assert result.promoted_count == 1
        assert "승격 항목" in result.promoted
        promoter.client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_promote_api_error_propagates(self):
        promoter = Promoter(api_key="test-key")
        promoter.client = AsyncMock()
        promoter.client.chat.completions.create = AsyncMock(
            side_effect=Exception("API Error")
        )

        with pytest.raises(Exception, match="API Error"):
            await promoter.promote(
                candidates=[{"ts": "t", "priority": "🔴", "content": "테스트"}],
                existing_persistent="",
            )


class TestCompactorCompact:
    @pytest.mark.asyncio
    async def test_compact_calls_api(self):
        compactor = Compactor(api_key="test-key", model="test-model")
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="<compacted>\n🔴 압축된 핵심\n</compacted>"
                )
            )
        ]
        compactor.client = AsyncMock()
        compactor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await compactor.compact(persistent="긴 기억", target_tokens=8000)

        assert "압축된 핵심" in result.compacted
        assert result.token_count > 0
        compactor.client.chat.completions.create.assert_called_once()


# ── Pipeline integration: _try_promote ───────────────────────


class TestTryPromote:
    @pytest.mark.asyncio
    async def test_skip_below_threshold(self, store):
        """임계치 미만이면 Promoter를 호출하지 않음"""
        mock_promoter = AsyncMock(spec=Promoter)
        token_counter = TokenCounter()

        await _try_promote(
            store=store,
            promoter=mock_promoter,
            promotion_threshold=5000,
            compactor=None,
            compaction_threshold=15000,
            compaction_target=8000,
            debug_channel="",
            token_counter=token_counter,
        )

        mock_promoter.promote.assert_not_called()

    @pytest.mark.asyncio
    async def test_promote_when_threshold_exceeded(self, store):
        """임계치 초과 시 Promoter 호출 후 장기 기억 저장"""
        # 후보 누적 (충분한 토큰)
        entries = [
            {"ts": "2026-02-10T00:00:00", "priority": "🔴", "content": f"후보 항목 {i} — " + "긴 설명 " * 50}
            for i in range(20)
        ]
        store.append_candidates("ts_1234", entries)

        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted="🔴 승격된 핵심 기억",
            rejected="- 기각된 항목",
            promoted_count=1,
            rejected_count=1,
            priority_counts={"🔴": 1},
        ))
        mock_promoter.merge_promoted = Promoter.merge_promoted

        token_counter = TokenCounter()

        await _try_promote(
            store=store,
            promoter=mock_promoter,
            promotion_threshold=10,  # 낮은 임계치
            compactor=None,
            compaction_threshold=15000,
            compaction_target=8000,
            debug_channel="",
            token_counter=token_counter,
        )

        mock_promoter.promote.assert_called_once()

        # 장기 기억이 저장되었는지 확인
        persistent = store.get_persistent()
        assert persistent is not None
        assert "승격된 핵심 기억" in persistent["content"]

        # 후보 버퍼가 비워졌는지 확인
        assert store.load_all_candidates() == []

    @pytest.mark.asyncio
    async def test_promote_no_promoted_items(self, store):
        """승격 항목이 없어도 후보 버퍼는 비워짐"""
        entries = [
            {"ts": "t", "priority": "🟢", "content": f"사소한 후보 {i} — " + "내용 " * 50}
            for i in range(20)
        ]
        store.append_candidates("ts_1234", entries)

        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted="",
            rejected="- 모두 기각",
            promoted_count=0,
            rejected_count=20,
        ))

        token_counter = TokenCounter()

        await _try_promote(
            store=store,
            promoter=mock_promoter,
            promotion_threshold=10,
            compactor=None,
            compaction_threshold=15000,
            compaction_target=8000,
            debug_channel="",
            token_counter=token_counter,
        )

        # 장기 기억은 저장되지 않음
        assert store.get_persistent() is None
        # 후보는 비워짐
        assert store.load_all_candidates() == []

    @pytest.mark.asyncio
    async def test_promote_triggers_compaction(self, store):
        """승격 후 장기 기억 토큰이 compaction 임계치를 넘으면 Compactor 호출"""
        # 기존에 장기 기억이 있는 상태
        store.save_persistent(
            content="기존 장기 기억 " * 500,
            meta={"token_count": 5000},
        )

        entries = [
            {"ts": "t", "priority": "🔴", "content": f"후보 {i} " + "긴 내용 " * 50}
            for i in range(20)
        ]
        store.append_candidates("ts_1234", entries)

        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted="🔴 " + "새 기억 " * 500,
            rejected="",
            promoted_count=1,
            rejected_count=0,
            priority_counts={"🔴": 1},
        ))
        mock_promoter.merge_promoted = Promoter.merge_promoted

        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(return_value=CompactorResult(
            compacted="🔴 압축된 핵심 기억",
            token_count=100,
        ))

        token_counter = TokenCounter()

        await _try_promote(
            store=store,
            promoter=mock_promoter,
            promotion_threshold=10,
            compactor=mock_compactor,
            compaction_threshold=50,  # 매우 낮은 임계치
            compaction_target=30,
            debug_channel="",
            token_counter=token_counter,
        )

        mock_compactor.compact.assert_called_once()

        # 압축 결과가 저장되었는지 확인
        persistent = store.get_persistent()
        assert "압축된 핵심 기억" in persistent["content"]

    @pytest.mark.asyncio
    async def test_promote_error_does_not_propagate(self, store):
        """Promoter 오류가 전파되지 않음"""
        entries = [
            {"ts": "t", "priority": "🔴", "content": f"후보 {i} " + "내용 " * 50}
            for i in range(20)
        ]
        store.append_candidates("ts_1234", entries)

        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(side_effect=Exception("API 오류"))

        token_counter = TokenCounter()

        # 예외가 전파되지 않음
        await _try_promote(
            store=store,
            promoter=mock_promoter,
            promotion_threshold=10,
            compactor=None,
            compaction_threshold=15000,
            compaction_target=8000,
            debug_channel="",
            token_counter=token_counter,
        )


# ── Pipeline integration: _try_compact ───────────────────────


class TestTryCompact:
    @pytest.mark.asyncio
    async def test_compact_archives_and_saves(self, store):
        """Compactor가 archive 후 압축 결과를 저장"""
        store.save_persistent(
            content="긴 장기 기억 " * 500,
            meta={"token_count": 16000},
        )

        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(return_value=CompactorResult(
            compacted="🔴 압축된 기억",
            token_count=100,
        ))

        await _try_compact(
            store=store,
            compactor=mock_compactor,
            compaction_target=8000,
            persistent_tokens=16000,
            debug_channel="",
        )

        mock_compactor.compact.assert_called_once()

        # 압축 결과 확인
        persistent = store.get_persistent()
        assert "압축된 기억" in persistent["content"]

        # archive가 생성되었는지 확인
        archive_dir = store._persistent_archive_dir()
        archive_files = list(archive_dir.glob("*.md"))
        assert len(archive_files) == 1

    @pytest.mark.asyncio
    async def test_compact_error_does_not_propagate(self, store):
        """Compactor 오류가 전파되지 않음"""
        store.save_persistent(content="기억", meta={})

        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(side_effect=Exception("API 오류"))

        await _try_compact(
            store=store,
            compactor=mock_compactor,
            compaction_target=8000,
            persistent_tokens=16000,
            debug_channel="",
        )


# ── Pipeline E2E: observe + promote ─────────────────────────


class TestObserveWithPromoter:
    @pytest.mark.asyncio
    async def test_observe_triggers_promoter(self, store, mock_observer, sample_messages):
        """관찰 후 후보 토큰이 충분하면 Promoter가 트리거됨"""
        # 미리 후보를 많이 쌓아둠
        big_entries = [
            {"ts": "t", "priority": "🔴", "content": f"기존 후보 {i} " + "내용 " * 50}
            for i in range(30)
        ]
        store.append_candidates("ts_other", big_entries)

        mock_observer.observe.return_value = ObserverResult(
            observations="관찰 내용",
            candidates="🔴 새 후보 항목",
        )

        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted="🔴 승격 기억",
            rejected="",
            promoted_count=1,
            rejected_count=0,
            priority_counts={"🔴": 1},
        ))
        mock_promoter.merge_promoted = Promoter.merge_promoted

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_1234",
            user_id="U12345",
            messages=sample_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=10,  # 낮은 임계치
        )

        assert result is True
        mock_promoter.promote.assert_called_once()

        persistent = store.get_persistent()
        assert persistent is not None
        assert "승격 기억" in persistent["content"]

    @pytest.mark.asyncio
    async def test_observe_no_promoter(self, store, mock_observer, sample_messages):
        """promoter가 None이면 승격 단계를 건너뜀"""
        mock_observer.observe.return_value = ObserverResult(
            observations="관찰 내용",
            candidates="🔴 후보",
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_1234",
            user_id="U12345",
            messages=sample_messages,
            min_turn_tokens=0,
            promoter=None,
        )

        assert result is True
        assert store.get_persistent() is None


# ── Debug log tests ──────────────────────────────────────────


class TestDebugLogs:
    @pytest.mark.asyncio
    async def test_promoter_debug_logs(self, store):
        """Promoter 디버그 로그 이벤트 #4, #5 발송"""
        entries = [
            {"ts": "t", "priority": "🔴", "content": f"후보 {i} " + "내용 " * 50}
            for i in range(20)
        ]
        store.append_candidates("ts_1234", entries)

        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted="🔴 승격 기억",
            rejected="- 기각",
            promoted_count=1,
            rejected_count=1,
            priority_counts={"🔴": 1},
        ))
        mock_promoter.merge_promoted = Promoter.merge_promoted

        token_counter = TokenCounter()

        with patch(
            "seosoyoung.memory.observation_pipeline._send_debug_log",
            return_value="debug_ts_1",
        ) as mock_send, patch(
            "seosoyoung.memory.observation_pipeline._update_debug_log",
        ) as mock_update:
            await _try_promote(
                store=store,
                promoter=mock_promoter,
                promotion_threshold=10,
                compactor=None,
                compaction_threshold=15000,
                compaction_target=8000,
                debug_channel="C_DEBUG",
                token_counter=token_counter,
            )

        # 이벤트 #4: Promoter 시작 (send)
        mock_send.assert_called_once()
        send_text = mock_send.call_args[0][1]
        assert "LTM 승격 검토 시작" in send_text

        # 이벤트 #5: Promoter 완료 (update)
        mock_update.assert_called_once()
        update_text = mock_update.call_args[0][2]
        assert "LTM 승격 완료" in update_text
        assert "승격 1건" in update_text
        assert "기각 1건" in update_text

    @pytest.mark.asyncio
    async def test_compactor_debug_log(self, store):
        """Compactor 디버그 로그 이벤트 #6 발송"""
        store.save_persistent(content="긴 기억 " * 500, meta={})

        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(return_value=CompactorResult(
            compacted="압축 기억",
            token_count=100,
        ))

        with patch(
            "seosoyoung.memory.observation_pipeline._send_debug_log",
            return_value="debug_ts_2",
        ) as mock_send:
            await _try_compact(
                store=store,
                compactor=mock_compactor,
                compaction_target=8000,
                persistent_tokens=16000,
                debug_channel="C_DEBUG",
            )

        mock_send.assert_called_once()
        send_text = mock_send.call_args[0][1]
        assert "LTM 장기 기억 압축" in send_text
        assert "archive" in send_text
