"""Reflector 단위 테스트"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from seosoyoung.memory.reflector import Reflector, ReflectorResult, _extract_observations


class TestExtractObservations:
    def test_extracts_from_xml_tag(self):
        text = "<observations>\n## [2026-02-10] Compressed\n\n🔴 핵심 관찰\n</observations>"
        result = _extract_observations(text)
        assert "핵심 관찰" in result
        assert "<observations>" not in result

    def test_fallback_to_full_text(self):
        text = "관찰 로그 압축 결과입니다.\n🔴 핵심 관찰"
        result = _extract_observations(text)
        assert result == text.strip()

    def test_empty_tag(self):
        text = "<observations></observations>"
        result = _extract_observations(text)
        assert result == ""

    def test_multiline_content(self):
        text = """<observations>
## [2026-02-10] Session
🔴 First observation

## [2026-02-09] Session
🟡 Second observation
</observations>"""
        result = _extract_observations(text)
        assert "First observation" in result
        assert "Second observation" in result


class TestReflector:
    @pytest.fixture
    def mock_openai_client(self):
        client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_reflect_success_under_target(self):
        """1차 시도에서 목표 이하면 바로 반환"""
        reflector = Reflector(api_key="test-key")

        compressed = "<observations>\n🔴 압축된 관찰\n</observations>"
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=compressed))]

        with patch.object(
            reflector.client.chat.completions, "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reflector.reflect(
                observations="긴 관찰 로그 " * 100,
                target_tokens=50000,  # 매우 높은 목표
            )

        assert result is not None
        assert "압축된 관찰" in result.observations
        assert result.token_count > 0

    @pytest.mark.asyncio
    async def test_reflect_retry_when_over_target(self):
        """1차 시도에서 목표 초과 시 재시도"""
        reflector = Reflector(api_key="test-key")

        # 1차: 긴 결과
        first_response = MagicMock()
        first_text = "<observations>\n" + ("🔴 관찰 " * 500) + "\n</observations>"
        first_response.choices = [MagicMock(message=MagicMock(content=first_text))]

        # 2차: 짧은 결과
        second_response = MagicMock()
        second_text = "<observations>\n🔴 압축된 관찰\n</observations>"
        second_response.choices = [MagicMock(message=MagicMock(content=second_text))]

        call_count = [0]
        async def mock_create(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return first_response
            return second_response

        with patch.object(
            reflector.client.chat.completions, "create",
            side_effect=mock_create,
        ):
            result = await reflector.reflect(
                observations="긴 관찰 로그 " * 100,
                target_tokens=10,  # 매우 낮은 목표 → 재시도 유발
            )

        assert result is not None
        assert call_count[0] == 2  # 2번 호출

    @pytest.mark.asyncio
    async def test_reflect_api_error_returns_none(self):
        """API 오류 시 None 반환"""
        reflector = Reflector(api_key="test-key")

        with patch.object(
            reflector.client.chat.completions, "create",
            new_callable=AsyncMock,
            side_effect=Exception("API 오류"),
        ):
            result = await reflector.reflect(observations="관찰 로그")

        assert result is None

    @pytest.mark.asyncio
    async def test_reflect_empty_response(self):
        """빈 응답 처리"""
        reflector = Reflector(api_key="test-key")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=""))]

        with patch.object(
            reflector.client.chat.completions, "create",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reflector.reflect(
                observations="관찰 로그",
                target_tokens=50000,
            )

        assert result is not None
        assert result.observations == ""


class TestPipelineReflectorIntegration:
    """observation_pipeline에 Reflector가 통합되었는지 테스트"""

    @pytest.fixture
    def store(self, tmp_path):
        from seosoyoung.memory.store import MemoryStore
        return MemoryStore(base_dir=tmp_path)

    @pytest.fixture
    def mock_observer(self):
        observer = AsyncMock()
        return observer

    @pytest.fixture
    def mock_reflector(self):
        reflector = AsyncMock()
        return reflector

    @pytest.mark.asyncio
    async def test_reflector_triggered_when_over_threshold(
        self, store, mock_observer, mock_reflector
    ):
        """관찰 토큰이 임계치 초과 시 Reflector 호출"""
        from seosoyoung.memory.observation_pipeline import observe_conversation
        from seosoyoung.memory.observer import ObserverResult

        # 긴 관찰 결과
        long_observations = "🔴 관찰 " * 5000
        mock_observer.observe.return_value = ObserverResult(
            observations=long_observations,
        )
        mock_reflector.reflect.return_value = ReflectorResult(
            observations="🔴 압축된 관찰",
            token_count=100,
        )

        result = await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_1234",
            user_id="U12345",
            messages=[{"role": "user", "content": "test"}],
            observation_threshold=0,
            reflector=mock_reflector,
            reflection_threshold=100,  # 낮은 임계치
        )

        assert result is True
        mock_reflector.reflect.assert_called_once()
        record = store.get_record("ts_1234")
        assert record.observations == "🔴 압축된 관찰"
        assert record.reflection_count == 1

    @pytest.mark.asyncio
    async def test_reflector_not_triggered_when_under_threshold(
        self, store, mock_observer, mock_reflector
    ):
        """관찰 토큰이 임계치 이하면 Reflector 미호출"""
        from seosoyoung.memory.observation_pipeline import observe_conversation
        from seosoyoung.memory.observer import ObserverResult

        mock_observer.observe.return_value = ObserverResult(
            observations="🔴 짧은 관찰",
        )

        await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_1234",
            user_id="U12345",
            messages=[{"role": "user", "content": "test"}],
            observation_threshold=0,
            reflector=mock_reflector,
            reflection_threshold=999999,  # 높은 임계치
        )

        mock_reflector.reflect.assert_not_called()

    @pytest.mark.asyncio
    async def test_reflector_none_means_no_compression(
        self, store, mock_observer
    ):
        """Reflector 미전달 시 압축 건너뜀"""
        from seosoyoung.memory.observation_pipeline import observe_conversation
        from seosoyoung.memory.observer import ObserverResult

        long_obs = "🔴 관찰 " * 5000
        mock_observer.observe.return_value = ObserverResult(observations=long_obs)

        await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_1234",
            user_id="U12345",
            messages=[{"role": "user", "content": "test"}],
            observation_threshold=0,
            reflector=None,
            reflection_threshold=100,
        )

        record = store.get_record("ts_1234")
        assert record.observations == long_obs

    @pytest.mark.asyncio
    async def test_reflector_failure_keeps_original(
        self, store, mock_observer, mock_reflector
    ):
        """Reflector 실패 시 원본 관찰 유지"""
        from seosoyoung.memory.observation_pipeline import observe_conversation
        from seosoyoung.memory.observer import ObserverResult

        long_obs = "🔴 관찰 " * 5000
        mock_observer.observe.return_value = ObserverResult(observations=long_obs)
        mock_reflector.reflect.return_value = None  # Reflector 실패

        await observe_conversation(
            store=store,
            observer=mock_observer,
            thread_ts="ts_1234",
            user_id="U12345",
            messages=[{"role": "user", "content": "test"}],
            observation_threshold=0,
            reflector=mock_reflector,
            reflection_threshold=100,
        )

        record = store.get_record("ts_1234")
        assert record.observations == long_obs
        assert record.reflection_count == 0
