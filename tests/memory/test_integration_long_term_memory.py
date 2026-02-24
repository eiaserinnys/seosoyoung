"""장기 기억 시스템 통합 테스트

전체 파이프라인을 E2E로 검증합니다:
  매턴 Observer → candidates 수집 → Promoter 트리거
  → 장기 기억 승격 → Compactor → 세션 시작 시 주입

모든 LLM 호출은 모킹합니다.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.slackbot.memory.context_builder import ContextBuilder
from seosoyoung.slackbot.memory.observation_pipeline import observe_conversation
from seosoyoung.slackbot.memory.observer import ObserverResult
from seosoyoung.slackbot.memory.promoter import Compactor, CompactorResult, Promoter, PromoterResult
from seosoyoung.slackbot.memory.reflector import Reflector, ReflectorResult
from seosoyoung.slackbot.memory.store import MemoryRecord, MemoryStore
from seosoyoung.slackbot.memory.token_counter import TokenCounter


def _make_obs_items(items_data):
    """테스트 헬퍼: 관찰 항목 리스트 생성.

    items_data: [(priority, content), ...] 또는 [(priority, content, session_date), ...]
    """
    result = []
    for i, item in enumerate(items_data):
        if len(item) == 3:
            priority, content, session_date = item
        else:
            priority, content = item
            session_date = "2026-02-10"
        result.append({
            "id": f"obs_20260210_{i:03d}",
            "priority": priority,
            "content": content,
            "session_date": session_date,
            "created_at": "2026-02-10T00:00:00+00:00",
            "source": "observer",
        })
    return result


def _make_ltm_items(items_data):
    """테스트 헬퍼: 장기 기억 항목 리스트 생성.

    items_data: [(priority, content), ...]
    """
    result = []
    for i, (priority, content) in enumerate(items_data):
        result.append({
            "id": f"ltm_20260210_{i:03d}",
            "priority": priority,
            "content": content,
            "promoted_at": "2026-02-10T00:00:00+00:00",
        })
    return result


def _make_candidate_items(items_data):
    """테스트 헬퍼: 후보 항목 리스트 생성.

    items_data: [(priority, content), ...]
    """
    result = []
    for i, (priority, content) in enumerate(items_data):
        result.append({
            "ts": "t",
            "priority": priority,
            "content": content,
        })
    return result


@pytest.fixture
def store(tmp_path):
    return MemoryStore(base_dir=tmp_path)


@pytest.fixture
def mock_observer():
    observer = AsyncMock()
    observer.observe = AsyncMock()
    return observer


@pytest.fixture
def mock_promoter():
    promoter = AsyncMock(spec=Promoter)
    promoter.merge_promoted = Promoter.merge_promoted
    return promoter


@pytest.fixture
def mock_compactor():
    compactor = AsyncMock(spec=Compactor)
    return compactor


@pytest.fixture
def mock_reflector():
    reflector = AsyncMock(spec=Reflector)
    return reflector


@pytest.fixture
def long_messages():
    """최소 토큰 기준을 넘는 충분히 긴 메시지"""
    return [
        {
            "role": "user",
            "content": "캐릭터 정보를 찾아주세요. 펜릭스의 설정에 대해 상세히 알려주세요. "
            "특히 마법 체계와 성격 설정을 중점적으로 설명해주시면 좋겠습니다.",
        },
        {
            "role": "assistant",
            "content": "네, 펜릭스 캐릭터 설정을 상세히 안내드리겠습니다. "
            "펜릭스는 엠버 앤 블레이드의 핵심 캐릭터로, 고대 성채를 탐험하는 마법검사입니다. "
            "마법 체계는 원소 기반이며 화염과 빙결 계열에 특화되어 있습니다. "
            "성격은 냉정하면서도 동료에 대한 신뢰가 깊은 편입니다.",
        },
    ]


class TestE2EFullPipeline:
    """전체 파이프라인 E2E: Observer → 후보 수집 → Promoter → 장기 기억 → 주입"""

    @pytest.mark.asyncio
    async def test_full_pipeline_observation_to_injection(
        self, store, mock_observer, mock_promoter, long_messages
    ):
        """관찰 → 후보 수집 → 승격 → 주입까지 전체 흐름"""
        thread_ts = "ts_e2e_001"
        user_id = "U_TEST"

        # -- 1단계: 여러 턴에 걸쳐 Observer가 후보를 수집 --
        # 턴 1: 후보 생성
        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "캐릭터 정보 조회 중")]),
            candidates=[
                {"priority": "🔴", "content": "사용자는 커밋 메시지를 한국어로 작성하는 것을 선호한다"},
            ],
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts=thread_ts,
            user_id=user_id,
            messages=long_messages,
            min_turn_tokens=0,
            promoter=None,  # 아직 승격하지 않음 (후보 누적만)
        )
        assert result is True

        # 후보가 저장되었는지 확인
        candidates = store.load_candidates(thread_ts)
        assert len(candidates) == 1
        assert candidates[0]["priority"] == "🔴"

        # 턴 2: 추가 후보 생성
        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "캐릭터 정보 조회 완료")]),
            candidates=[
                {"priority": "🟡", "content": "트렐로 카드 작업 시 체크리스트를 먼저 확인하는 패턴"},
                {"priority": "🟢", "content": "eb_lore 폴더를 자주 참조"},
            ],
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts=thread_ts,
            user_id=user_id,
            messages=long_messages,
            min_turn_tokens=0,
            promoter=None,
        )
        assert result is True

        # 후보 누적 확인
        candidates = store.load_candidates(thread_ts)
        assert len(candidates) == 3

        # 다른 세션에서도 후보 생성
        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "Session B 관찰")]),
            candidates=[
                {"priority": "🔴", "content": "테스트 실행 전 항상 lint를 먼저 실행하는 패턴"},
            ],
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_e2e_002",
            user_id=user_id,
            messages=long_messages,
            min_turn_tokens=0,
            promoter=None,
        )
        assert result is True

        # 전체 후보 4건
        all_candidates = store.load_all_candidates()
        assert len(all_candidates) == 4

        # -- 2단계: Promoter가 후보를 검토하여 승격 --
        promoted_items = _make_ltm_items([
            ("🔴", "사용자는 커밋 메시지를 한국어로 작성하는 것을 선호한다"),
            ("🔴", "테스트 실행 전 항상 lint를 먼저 실행하는 패턴"),
        ])
        mock_promoter.promote = AsyncMock(
            return_value=PromoterResult(
                promoted=promoted_items,
                rejected=[{"priority": "🟢", "content": "eb_lore 폴더 참조 (세션 한정 맥락)"}],
                promoted_count=2,
                rejected_count=1,
                priority_counts={"🔴": 2},
            )
        )

        # 이번에는 promoter를 넘겨서 승격까지 수행
        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "Session C 관찰")]),
            candidates=[],  # 이번 턴에는 후보 없음
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_e2e_003",
            user_id=user_id,
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=1,  # 낮은 임계치 → 즉시 트리거
        )
        assert result is True

        # 장기 기억이 저장되었는지 확인
        persistent = store.get_persistent()
        assert persistent is not None
        assert any("커밋 메시지를 한국어로" in item["content"] for item in persistent["content"])
        assert any("lint를 먼저 실행" in item["content"] for item in persistent["content"])

        # 후보 버퍼가 비워졌는지 확인
        assert store.load_all_candidates() == []

        # -- 3단계: 세션 시작 시 장기 기억 + 세션 관찰 주입 --
        builder = ContextBuilder(store)

        # 장기 기억만 주입 (새 세션이라 세션 관찰 없음)
        injection = builder.build_memory_prompt(
            thread_ts="ts_new_session",
            include_persistent=True,
            include_session=True,
        )
        assert injection.prompt is not None
        assert "<long-term-memory>" in injection.prompt
        assert "커밋 메시지를 한국어로" in injection.prompt
        assert injection.persistent_tokens > 0
        # 세션 관찰은 없으므로
        assert "<observational-memory>" not in injection.prompt
        assert injection.session_tokens == 0

        # 기존 세션에서는 장기 기억 + 세션 관찰 모두 주입
        injection2 = builder.build_memory_prompt(
            thread_ts=thread_ts,
            include_persistent=True,
            include_session=True,
        )
        assert injection2.prompt is not None
        assert "<long-term-memory>" in injection2.prompt
        assert "<observational-memory>" in injection2.prompt
        assert injection2.persistent_tokens > 0
        assert injection2.session_tokens > 0

    @pytest.mark.asyncio
    async def test_full_pipeline_with_compaction(
        self, store, mock_observer, mock_promoter, mock_compactor, long_messages
    ):
        """승격 후 장기 기억이 크면 Compactor까지 호출되는 전체 흐름"""
        thread_ts = "ts_compact_001"

        # 기존에 큰 장기 기억이 있는 상태
        big_persistent = _make_ltm_items([
            ("🔴", "기존 장기 기억 " * 500),
        ])
        store.save_persistent(
            content=big_persistent,
            meta={"token_count": 10000},
        )

        # 후보 누적
        big_entries = _make_candidate_items([
            ("🔴", f"후보 {i} " + "긴 내용 " * 50)
            for i in range(20)
        ])
        store.append_candidates("ts_old_session", big_entries)

        # Promoter가 큰 승격 결과를 반환
        promoted = _make_ltm_items([("🔴", "새로운 핵심 기억 " * 500)])
        mock_promoter.promote = AsyncMock(
            return_value=PromoterResult(
                promoted=promoted,
                rejected=[],
                promoted_count=1,
                rejected_count=0,
                priority_counts={"🔴": 1},
            )
        )

        # Compactor가 압축 결과를 반환
        compacted = _make_ltm_items([("🔴", "압축된 핵심 장기 기억")])
        mock_compactor.compact = AsyncMock(
            return_value=CompactorResult(
                compacted=compacted,
                token_count=100,
            )
        )

        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "Session 관찰")]),
            candidates=[],
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts=thread_ts,
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=1,
            compactor=mock_compactor,
            compaction_threshold=50,  # 낮은 임계치 → 컴팩션 트리거
            compaction_target=30,
        )

        assert result is True
        mock_promoter.promote.assert_called_once()
        mock_compactor.compact.assert_called_once()

        # 최종 장기 기억은 압축된 결과
        persistent = store.get_persistent()
        assert persistent is not None
        assert any("압축된 핵심 장기 기억" in item["content"] for item in persistent["content"])

        # archive에 백업이 생겼는지 확인
        archive_dir = store._persistent_archive_dir()
        archive_files = list(archive_dir.glob("*.json"))
        assert len(archive_files) >= 1

    @pytest.mark.asyncio
    async def test_multi_session_candidates_merge(
        self, store, mock_observer, mock_promoter, long_messages
    ):
        """여러 세션에서 생성된 후보가 Promoter에 함께 전달됨"""
        sessions = ["ts_sess_1", "ts_sess_2", "ts_sess_3"]

        for i, session in enumerate(sessions):
            mock_observer.observe.return_value = ObserverResult(
                observations=_make_obs_items([(f"🔴", f"Session {i} 관찰")]),
                candidates=[
                    {"priority": "🔴", "content": f"세션 {i}의 핵심 관찰"},
                ],
            )

            await observe_conversation(
                store=store,
                observer=mock_observer,
                thread_ts=session,
                user_id="U_TEST",
                messages=long_messages,
                min_turn_tokens=0,
                promoter=None,  # 아직 승격하지 않음
            )

        # 전체 후보 3건
        all_candidates = store.load_all_candidates()
        assert len(all_candidates) == 3

        # Promoter 호출 시 모든 세션의 후보가 전달됨
        promoted = _make_ltm_items([
            ("🔴", "세션 0의 핵심 관찰"),
            ("🔴", "세션 1의 핵심 관찰"),
            ("🔴", "세션 2의 핵심 관찰"),
        ])
        mock_promoter.promote = AsyncMock(
            return_value=PromoterResult(
                promoted=promoted,
                rejected=[],
                promoted_count=3,
                rejected_count=0,
                priority_counts={"🔴": 3},
            )
        )

        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "Trigger session 관찰")]),
            candidates=[],
        )

        await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_trigger",
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=1,
        )

        mock_promoter.promote.assert_called_once()
        call_kwargs = mock_promoter.promote.call_args.kwargs
        # 후보 3건이 모두 전달되었는지
        assert len(call_kwargs["candidates"]) == 3

    @pytest.mark.asyncio
    async def test_reflector_then_promoter(
        self, store, mock_observer, mock_promoter, mock_reflector, long_messages
    ):
        """Reflector(세션 관찰 압축)와 Promoter(장기 기억 승격) 동시 동작"""
        # 후보를 미리 쌓아둠
        entries = _make_candidate_items([
            ("🔴", f"후보 {i} " + "내용 " * 50)
            for i in range(10)
        ])
        store.append_candidates("ts_old", entries)

        # Observer가 매우 긴 관찰과 후보를 반환
        long_observations = _make_obs_items([
            ("🟢", f"관찰 내용 {i} " + "상세 " * 100)
            for i in range(50)
        ])
        mock_observer.observe.return_value = ObserverResult(
            observations=long_observations,
            candidates=[
                {"priority": "🔴", "content": "새 후보 항목"},
            ],
        )

        compressed_obs = _make_obs_items([("🔴", "압축된 관찰")])
        mock_reflector.reflect = AsyncMock(
            return_value=ReflectorResult(
                observations=compressed_obs,
                token_count=100,
            )
        )

        promoted = _make_ltm_items([("🔴", "승격된 기억")])
        mock_promoter.promote = AsyncMock(
            return_value=PromoterResult(
                promoted=promoted,
                rejected=[],
                promoted_count=1,
                rejected_count=0,
                priority_counts={"🔴": 1},
            )
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_both",
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            reflector=mock_reflector,
            reflection_threshold=10,  # 낮은 임계치 → Reflector 트리거
            promoter=mock_promoter,
            promotion_threshold=1,  # 낮은 임계치 → Promoter 트리거
        )

        assert result is True

        # Reflector가 호출되었는지
        mock_reflector.reflect.assert_called_once()

        # 세션 관찰이 압축되었는지
        record = store.get_record("ts_both")
        assert record.observations == compressed_obs
        assert record.reflection_count == 1

        # Promoter도 호출되었는지
        mock_promoter.promote.assert_called_once()

        # 장기 기억 저장 확인
        persistent = store.get_persistent()
        assert persistent is not None
        assert any("승격된 기억" in item["content"] for item in persistent["content"])


class TestEdgeCases:
    """엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_no_candidates_ever(self, store, mock_observer, mock_promoter, long_messages):
        """후보가 한 번도 생성되지 않은 경우"""
        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "관찰만 있음")]),
            candidates=[],  # 후보 없음
        )

        for i in range(5):
            result = await observe_conversation(
                store=store,
                observer=mock_observer,
                thread_ts=f"ts_{i}",
                user_id="U_TEST",
                messages=long_messages,
                min_turn_tokens=0,
                promoter=mock_promoter,
                promotion_threshold=5000,
            )
            assert result is True

        # 후보가 없으므로 Promoter는 호출되지 않음
        mock_promoter.promote.assert_not_called()
        # 장기 기억도 없음
        assert store.get_persistent() is None

    @pytest.mark.asyncio
    async def test_promoter_rejects_all(self, store, mock_observer, mock_promoter, long_messages):
        """Promoter가 모든 후보를 기각하는 경우"""
        # 후보 쌓기
        entries = _make_candidate_items([
            ("🟢", f"사소한 후보 {i} " + "내용 " * 50)
            for i in range(15)
        ])
        store.append_candidates("ts_some", entries)

        mock_promoter.promote = AsyncMock(
            return_value=PromoterResult(
                promoted=[],
                rejected=[{"priority": "🟢", "content": "모든 항목이 일시적 맥락으로 판단됨"}],
                promoted_count=0,
                rejected_count=15,
            )
        )

        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "Session 관찰")]),
            candidates=[],
        )

        await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_reject",
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=1,
        )

        mock_promoter.promote.assert_called_once()
        # 장기 기억은 없어야 함
        assert store.get_persistent() is None
        # 후보 버퍼는 비워져야 함
        assert store.load_all_candidates() == []

    @pytest.mark.asyncio
    async def test_compaction_not_needed(self, store, mock_observer, mock_promoter, mock_compactor, long_messages):
        """승격 후 장기 기억이 compaction 임계치 미만인 경우 Compactor 미호출"""
        entries = _make_candidate_items([
            ("🔴", f"후보 {i} " + "내용 " * 50)
            for i in range(10)
        ])
        store.append_candidates("ts_small", entries)

        promoted = _make_ltm_items([("🔴", "작은 기억")])
        mock_promoter.promote = AsyncMock(
            return_value=PromoterResult(
                promoted=promoted,
                rejected=[],
                promoted_count=1,
                rejected_count=0,
                priority_counts={"🔴": 1},
            )
        )

        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "Session 관찰")]),
            candidates=[],
        )

        await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_no_compact",
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=1,
            compactor=mock_compactor,
            compaction_threshold=999999,  # 매우 높은 임계치 → 컴팩션 트리거 안됨
            compaction_target=500000,
        )

        mock_promoter.promote.assert_called_once()
        mock_compactor.compact.assert_not_called()

        # 장기 기억은 승격 결과 그대로
        persistent = store.get_persistent()
        assert persistent is not None
        assert any("작은 기억" in item["content"] for item in persistent["content"])

    @pytest.mark.asyncio
    async def test_no_persistent_memory_for_user(self, store, long_messages):
        """장기 기억이 없는 사용자에 대한 세션 시작"""
        builder = ContextBuilder(store)

        # 장기 기억도 세션 관찰도 없는 상태
        injection = builder.build_memory_prompt(
            thread_ts="ts_new_user",
            include_persistent=True,
            include_session=True,
        )

        assert injection.prompt is None
        assert injection.persistent_tokens == 0
        assert injection.session_tokens == 0

    @pytest.mark.asyncio
    async def test_observer_error_does_not_break_pipeline(
        self, store, mock_observer, mock_promoter, long_messages
    ):
        """Observer 오류가 발생해도 파이프라인이 중단되지 않음"""
        mock_observer.observe.side_effect = Exception("LLM API 오류")

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_error",
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
        )

        assert result is False
        mock_promoter.promote.assert_not_called()

    @pytest.mark.asyncio
    async def test_promoter_error_does_not_break_observation(
        self, store, mock_observer, mock_promoter, long_messages
    ):
        """Promoter 오류가 발생해도 관찰 자체는 성공"""
        # 후보를 미리 쌓아둠
        entries = _make_candidate_items([
            ("🔴", f"후보 {i} " + "내용 " * 50)
            for i in range(10)
        ])
        store.append_candidates("ts_old", entries)

        obs_items = _make_obs_items([("🔴", "관찰 성공")])
        mock_observer.observe.return_value = ObserverResult(
            observations=obs_items,
            candidates=[
                {"priority": "🔴", "content": "새 후보"},
            ],
        )

        mock_promoter.promote = AsyncMock(side_effect=Exception("Promoter API 오류"))

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_promoter_fail",
            user_id="U_TEST",
            messages=long_messages,
            min_turn_tokens=0,
            promoter=mock_promoter,
            promotion_threshold=1,
        )

        # 관찰 자체는 성공
        assert result is True
        record = store.get_record("ts_promoter_fail")
        assert record is not None
        assert any("관찰 성공" in item["content"] for item in record.observations)


class TestInjectionIntegration:
    """주입 통합 테스트 - ContextBuilder와 Store의 연동"""

    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def builder(self, store):
        return ContextBuilder(store)

    def test_injection_persistent_only(self, builder, store):
        """장기 기억만 있을 때 주입"""
        store.save_persistent(
            content=_make_ltm_items([
                ("🔴", "사용자는 한국어 커밋 메시지를 선호"),
                ("🟡", "트렐로 체크리스트 먼저 확인"),
            ]),
            meta={"token_count": 100},
        )

        injection = builder.build_memory_prompt(
            "ts_new_session",
            include_persistent=True,
            include_session=True,
        )

        assert injection.prompt is not None
        assert "<long-term-memory>" in injection.prompt
        assert "한국어 커밋 메시지를 선호" in injection.prompt
        assert "<observational-memory>" not in injection.prompt

    def test_injection_session_only(self, builder, store):
        """세션 관찰만 있을 때 주입 (장기 기억 없음)"""
        store.save_record(MemoryRecord(
            thread_ts="ts_session",
            user_id="U_TEST",
            observations=_make_obs_items([("🔴", "이번 세션 관찰")]),
        ))

        injection = builder.build_memory_prompt(
            "ts_session",
            include_persistent=True,
            include_session=True,
        )

        assert injection.prompt is not None
        assert "<observational-memory>" in injection.prompt
        assert "<long-term-memory>" not in injection.prompt

    def test_injection_both_layers(self, builder, store):
        """장기 기억 + 세션 관찰 모두 주입"""
        store.save_persistent(
            content=_make_ltm_items([("🔴", "장기 기억 내용")]),
            meta={"token_count": 50},
        )
        store.save_record(MemoryRecord(
            thread_ts="ts_both",
            user_id="U_TEST",
            observations=_make_obs_items([("🟡", "세션 관찰 내용")]),
        ))

        injection = builder.build_memory_prompt(
            "ts_both",
            include_persistent=True,
            include_session=True,
        )

        assert injection.prompt is not None
        assert "<long-term-memory>" in injection.prompt
        assert "<observational-memory>" in injection.prompt
        assert "장기 기억 내용" in injection.prompt
        assert "세션 관찰 내용" in injection.prompt
        # 장기 기억이 세션 관찰보다 먼저 나와야 함
        ltm_pos = injection.prompt.index("<long-term-memory>")
        om_pos = injection.prompt.index("<observational-memory>")
        assert ltm_pos < om_pos

    def test_injection_respects_include_flags(self, builder, store):
        """include_persistent / include_session 플래그가 정확히 동작"""
        store.save_persistent(
            content=_make_ltm_items([("🔴", "장기 기억")]),
            meta={},
        )
        store.save_record(MemoryRecord(
            thread_ts="ts_flags",
            user_id="U_TEST",
            observations=_make_obs_items([("🟡", "세션 관찰")]),
        ))

        # persistent=False, session=True
        result = builder.build_memory_prompt(
            "ts_flags", include_persistent=False, include_session=True,
        )
        assert result.prompt is not None
        assert "<long-term-memory>" not in result.prompt
        assert "<observational-memory>" in result.prompt

        # persistent=True, session=False
        result = builder.build_memory_prompt(
            "ts_flags", include_persistent=True, include_session=False,
        )
        assert result.prompt is not None
        assert "<long-term-memory>" in result.prompt
        assert "<observational-memory>" not in result.prompt

        # persistent=False, session=False
        result = builder.build_memory_prompt(
            "ts_flags", include_persistent=False, include_session=False,
        )
        assert result.prompt is None


class TestMigrationE2E:
    """기존 .md 데이터 → 자동 마이그레이션 → JSON 파이프라인 정상 동작"""

    @pytest.fixture
    def store(self, tmp_path):
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def mock_observer(self):
        observer = AsyncMock()
        observer.observe = AsyncMock()
        return observer

    @pytest.fixture
    def long_messages(self):
        return [
            {"role": "user", "content": "캐릭터 정보를 찾아주세요. " * 10},
            {"role": "assistant", "content": "네, 안내 드리겠습니다. " * 10},
        ]

    @pytest.mark.asyncio
    async def test_md_observations_auto_migrate_then_observe(
        self, store, mock_observer, long_messages
    ):
        """기존 .md 관찰 데이터가 있는 세션에서 새 관찰을 수행하면
        자동 마이그레이션 후 JSON 기반으로 정상 동작"""
        thread_ts = "ts_legacy_001"
        store._ensure_dirs()

        # 레거시 .md 관찰 데이터 직접 배치
        meta = {
            "thread_ts": thread_ts,
            "user_id": "U_LEGACY",
            "username": "legacy_user",
            "observation_tokens": 50,
            "total_sessions_observed": 2,
            "reflection_count": 0,
            "created_at": "2026-02-10T00:00:00+00:00",
        }
        store._meta_path(thread_ts).write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )

        md_content = (
            "## [2026-02-10] Session Observations\n"
            "🔴 사용자는 커밋 메시지를 한글로 작성하는 것을 선호\n"
            "🟡 트렐로 체크리스트를 먼저 확인하는 패턴\n"
        )
        store._obs_md_path(thread_ts).write_text(md_content, encoding="utf-8")

        # get_record로 자동 마이그레이션 트리거
        record = store.get_record(thread_ts)
        assert record is not None
        assert len(record.observations) == 2
        assert record.observations[0]["source"] == "migrated"
        assert not store._obs_md_path(thread_ts).exists()
        assert store._obs_path(thread_ts).exists()

        # 마이그레이션된 데이터 위에 새 관찰 수행
        mock_observer.observe.return_value = ObserverResult(
            observations=[
                *record.observations,
                {
                    "priority": "🔴",
                    "content": "새로운 관찰 추가됨",
                    "session_date": "2026-02-10",
                },
            ],
            candidates=[],
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts=thread_ts,
            user_id="U_LEGACY",
            messages=long_messages,
            min_turn_tokens=0,
        )

        assert result is True

        updated_record = store.get_record(thread_ts)
        assert len(updated_record.observations) == 3
        assert any("새로운 관찰 추가됨" in item["content"] for item in updated_record.observations)

    @pytest.mark.asyncio
    async def test_md_persistent_auto_migrate_then_inject(self, store):
        """기존 .md 장기 기억 → 자동 마이그레이션 → ContextBuilder 주입"""
        store._ensure_dirs()

        md_content = "🔴 사용자는 한국어 커밋 메시지를 선호\n🟡 체크리스트 먼저 확인\n"
        store._persistent_md_path().write_text(md_content, encoding="utf-8")

        # get_persistent로 자동 마이그레이션 트리거
        persistent = store.get_persistent()
        assert persistent is not None
        assert len(persistent["content"]) == 2
        assert not store._persistent_md_path().exists()
        assert store._persistent_content_path().exists()

        # ContextBuilder로 주입 확인
        builder = ContextBuilder(store)
        injection = builder.build_memory_prompt(
            "ts_new_session",
            include_persistent=True,
            include_session=True,
        )

        assert injection.prompt is not None
        assert "<long-term-memory>" in injection.prompt
        assert "한국어 커밋 메시지를 선호" in injection.prompt
        assert injection.persistent_tokens > 0

    @pytest.mark.asyncio
    async def test_bulk_migration_then_pipeline(
        self, store, mock_observer, long_messages
    ):
        """일괄 마이그레이션 모듈 실행 후 파이프라인이 정상 동작"""
        from seosoyoung.slackbot.memory.migration import migrate_memory_dir

        store._ensure_dirs()

        # 여러 세션의 .md 파일 배치
        for i in range(3):
            ts = f"ts_bulk_{i:03d}"
            meta = {"thread_ts": ts, "user_id": "U_BULK", "total_sessions_observed": 1}
            store._meta_path(ts).write_text(
                json.dumps(meta), encoding="utf-8"
            )
            store._obs_md_path(ts).write_text(
                f"## [2026-02-1{i}] Session\n🔴 세션 {i}의 관찰\n",
                encoding="utf-8",
            )

        # 장기 기억 .md
        store._persistent_md_path().write_text(
            "🔴 기존 장기 기억\n", encoding="utf-8"
        )

        # 일괄 마이그레이션 실행
        report = migrate_memory_dir(store.base_dir)

        assert report.total_converted == 4  # 3 obs + 1 persistent
        assert len(report.errors) == 0

        # 마이그레이션 후 각 세션을 정상 로드
        for i in range(3):
            ts = f"ts_bulk_{i:03d}"
            record = store.get_record(ts)
            assert record is not None
            assert len(record.observations) == 1
            assert record.observations[0]["content"] == f"세션 {i}의 관찰"

        # 장기 기억도 정상 로드
        persistent = store.get_persistent()
        assert persistent is not None
        assert persistent["content"][0]["content"] == "기존 장기 기억"

        # 마이그레이션 후 새 관찰도 정상 동작
        mock_observer.observe.return_value = ObserverResult(
            observations=_make_obs_items([("🔴", "마이그레이션 후 새 관찰")]),
            candidates=[],
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_bulk_000",
            user_id="U_BULK",
            messages=long_messages,
            min_turn_tokens=0,
        )
        assert result is True
