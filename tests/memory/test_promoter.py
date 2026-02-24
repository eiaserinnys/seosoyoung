"""Promoter / Compactor 모듈 + 파이프라인 연동 테스트"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.slackbot.memory.promoter import (
    Compactor,
    CompactorResult,
    Promoter,
    PromoterResult,
    parse_compactor_output,
    parse_promoter_output,
)
from seosoyoung.slackbot.memory.observation_pipeline import (
    _try_compact,
    _try_promote,
    observe_conversation,
)
from seosoyoung.slackbot.memory.observer import ObserverResult
from seosoyoung.slackbot.memory.store import MemoryStore
from seosoyoung.slackbot.memory.token_counter import TokenCounter


def _make_ltm_item(**overrides):
    defaults = {
        "id": "ltm_20260210_000",
        "priority": "🔴",
        "content": "장기 기억",
        "promoted_at": "2026-02-10T15:30:00+00:00",
    }
    defaults.update(overrides)
    return defaults


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


class TestParsePromoterOutput:
    def test_parse_full(self):
        data = {
            "promoted": [
                {"priority": "🔴", "content": "한국어 커밋 선호"},
                {"priority": "🟡", "content": "체크리스트 패턴"},
            ],
            "rejected": [
                {"reason": "일시적 맥락", "content": "세션 한정"},
                {"reason": "불필요", "content": "단순 인사"},
            ],
        }
        text = json.dumps(data)
        result = parse_promoter_output(text)
        assert result.promoted_count == 2
        assert result.rejected_count == 2
        assert result.priority_counts == {"🔴": 1, "🟡": 1}
        assert any("한국어 커밋 선호" in p["content"] for p in result.promoted)

    def test_parse_no_promoted(self):
        data = {"promoted": [], "rejected": [{"content": "모두 기각"}]}
        text = json.dumps(data)
        result = parse_promoter_output(text)
        assert result.promoted_count == 0
        assert result.rejected_count == 1

    def test_parse_no_tags(self):
        text = "일반 텍스트"
        result = parse_promoter_output(text)
        assert result.promoted == []
        assert result.rejected == []

    def test_parse_json_in_codeblock(self):
        data = {"promoted": [{"priority": "🔴", "content": "코드블록 테스트"}], "rejected": []}
        text = f"```json\n{json.dumps(data)}\n```"
        result = parse_promoter_output(text)
        assert result.promoted_count == 1

    def test_promoted_items_get_ids(self):
        data = {"promoted": [{"priority": "🔴", "content": "테스트"}], "rejected": []}
        text = json.dumps(data)
        result = parse_promoter_output(text)
        assert result.promoted[0].get("id") is not None
        assert result.promoted[0]["id"].startswith("ltm_")


class TestParseCompactorOutput:
    def test_parse_compacted(self):
        data = [
            {"priority": "🔴", "content": "압축된 핵심"},
            {"priority": "🟡", "content": "유지된 맥락"},
        ]
        text = json.dumps(data)
        result = parse_compactor_output(text)
        assert len(result) == 2
        assert result[0]["content"] == "압축된 핵심"

    def test_fallback_on_invalid_json(self):
        existing = [_make_ltm_item()]
        result = parse_compactor_output("태그 없는 결과", existing)
        assert result == existing  # fallback: 기존 항목 유지


# ── Promoter class ───────────────────────────────────────────


class TestPromoterMerge:
    def test_merge_both(self):
        existing = [_make_ltm_item(id="ltm_1", content="기존 기억")]
        promoted = [_make_ltm_item(id="ltm_2", content="새 기억")]
        result = Promoter.merge_promoted(existing, promoted)
        assert len(result) == 2
        assert any(i["content"] == "기존 기억" for i in result)
        assert any(i["content"] == "새 기억" for i in result)

    def test_merge_no_existing(self):
        promoted = [_make_ltm_item(content="새 기억")]
        assert Promoter.merge_promoted([], promoted) == promoted

    def test_merge_no_promoted(self):
        existing = [_make_ltm_item(content="기존 기억")]
        assert Promoter.merge_promoted(existing, []) == existing

    def test_merge_updates_existing_by_id(self):
        existing = [_make_ltm_item(id="ltm_1", content="원래 내용", priority="🟡")]
        promoted = [_make_ltm_item(id="ltm_1", content="업데이트 내용", priority="🔴")]
        result = Promoter.merge_promoted(existing, promoted)
        assert len(result) == 1
        assert result[0]["content"] == "업데이트 내용"
        assert result[0]["priority"] == "🔴"


class TestPromoterPromote:
    @pytest.mark.asyncio
    async def test_promote_calls_api(self):
        promoter = Promoter(api_key="test-key", model="test-model")
        response_data = {
            "promoted": [{"priority": "🔴", "content": "승격 항목"}],
            "rejected": [{"content": "기각"}],
        }
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content=json.dumps(response_data))
            )
        ]
        promoter.client = AsyncMock()
        promoter.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await promoter.promote(
            candidates=[{"ts": "t", "priority": "🔴", "content": "테스트"}],
            existing_persistent=[],
        )

        assert result.promoted_count == 1
        assert "승격 항목" in result.promoted[0]["content"]
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
                existing_persistent=[],
            )


class TestCompactorCompact:
    @pytest.mark.asyncio
    async def test_compact_calls_api(self):
        compactor = Compactor(api_key="test-key", model="test-model")
        response_data = [{"priority": "🔴", "content": "압축된 핵심"}]
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(content=json.dumps(response_data))
            )
        ]
        compactor.client = AsyncMock()
        compactor.client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await compactor.compact(persistent=[_make_ltm_item()], target_tokens=8000)

        assert len(result.compacted) >= 1
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

        promoted_items = [_make_ltm_item(content="승격된 핵심 기억")]
        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted=promoted_items,
            rejected=[{"content": "기각된 항목"}],
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
        assert any("승격된 핵심 기억" in item["content"] for item in persistent["content"])

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
            promoted=[],
            rejected=[{"content": "모두 기각"}],
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
        existing_items = [_make_ltm_item(id=f"ltm_e{i}", content="기존 장기 기억 " * 50) for i in range(10)]
        store.save_persistent(
            content=existing_items,
            meta={"token_count": 5000},
        )

        entries = [
            {"ts": "t", "priority": "🔴", "content": f"후보 {i} " + "긴 내용 " * 50}
            for i in range(20)
        ]
        store.append_candidates("ts_1234", entries)

        new_items = [_make_ltm_item(id="ltm_new_0", content="새 기억 " * 500)]
        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted=new_items,
            rejected=[],
            promoted_count=1,
            rejected_count=0,
            priority_counts={"🔴": 1},
        ))
        mock_promoter.merge_promoted = Promoter.merge_promoted

        compacted_items = [_make_ltm_item(id="ltm_c0", content="압축된 핵심 기억")]
        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(return_value=CompactorResult(
            compacted=compacted_items,
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
        assert any("압축된 핵심 기억" in item["content"] for item in persistent["content"])

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
        existing_items = [_make_ltm_item(content="긴 장기 기억 " * 50)]
        store.save_persistent(
            content=existing_items,
            meta={"token_count": 16000},
        )

        compacted_items = [_make_ltm_item(id="ltm_c0", content="압축된 기억")]
        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(return_value=CompactorResult(
            compacted=compacted_items,
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
        assert any("압축된 기억" in item["content"] for item in persistent["content"])

        # archive가 생성되었는지 확인
        archive_dir = store._persistent_archive_dir()
        archive_files = list(archive_dir.glob("*.json"))
        assert len(archive_files) == 1

    @pytest.mark.asyncio
    async def test_compact_error_does_not_propagate(self, store):
        """Compactor 오류가 전파되지 않음"""
        store.save_persistent(content=[_make_ltm_item()], meta={})

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
            observations=[{
                "id": "obs_20260210_000",
                "priority": "🔴",
                "content": "관찰 내용",
                "session_date": "2026-02-10",
                "created_at": "2026-02-10T09:30:00+00:00",
                "source": "observer",
            }],
            candidates=[{"ts": "t", "priority": "🔴", "content": "새 후보 항목"}],
        )

        promoted_items = [_make_ltm_item(content="승격 기억")]
        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted=promoted_items,
            rejected=[],
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
        assert any("승격 기억" in item["content"] for item in persistent["content"])

    @pytest.mark.asyncio
    async def test_observe_no_promoter(self, store, mock_observer, sample_messages):
        """promoter가 None이면 승격 단계를 건너뜀"""
        mock_observer.observe.return_value = ObserverResult(
            observations=[{
                "id": "obs_20260210_000",
                "priority": "🔴",
                "content": "관찰 내용",
                "session_date": "2026-02-10",
                "created_at": "2026-02-10T09:30:00+00:00",
                "source": "observer",
            }],
            candidates=[{"ts": "t", "priority": "🔴", "content": "후보"}],
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

        promoted_items = [_make_ltm_item(content="승격 기억")]
        mock_promoter = AsyncMock(spec=Promoter)
        mock_promoter.promote = AsyncMock(return_value=PromoterResult(
            promoted=promoted_items,
            rejected=[{"content": "기각"}],
            promoted_count=1,
            rejected_count=1,
            priority_counts={"🔴": 1},
        ))
        mock_promoter.merge_promoted = Promoter.merge_promoted

        token_counter = TokenCounter()

        with patch(
            "seosoyoung.slackbot.memory.observation_pipeline._send_debug_log",
            return_value="debug_ts_1",
        ) as mock_send, patch(
            "seosoyoung.slackbot.memory.observation_pipeline._update_debug_log",
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
        store.save_persistent(content=[_make_ltm_item(content="긴 기억 " * 50)], meta={})

        compacted_items = [_make_ltm_item(id="ltm_c0", content="압축 기억")]
        mock_compactor = AsyncMock(spec=Compactor)
        mock_compactor.compact = AsyncMock(return_value=CompactorResult(
            compacted=compacted_items,
            token_count=100,
        ))

        with patch(
            "seosoyoung.slackbot.memory.observation_pipeline._send_debug_log",
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
