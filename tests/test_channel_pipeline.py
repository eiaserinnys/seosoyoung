"""채널 소화 파이프라인 통합 테스트"""

import json
from pathlib import Path

import pytest

from seosoyoung.memory.channel_observer import (
    ChannelObserverResult,
    DigestCompressorResult,
)
from seosoyoung.memory.channel_pipeline import digest_channel
from seosoyoung.memory.channel_store import ChannelStore


@pytest.fixture
def store(tmp_path):
    return ChannelStore(base_dir=tmp_path)


@pytest.fixture
def channel_id():
    return "C_TEST_CHANNEL"


def _fill_buffer(store: ChannelStore, channel_id: str, n: int = 10):
    """버퍼에 테스트 메시지를 채운다."""
    for i in range(n):
        store.append_channel_message(channel_id, {
            "ts": f"100{i}.000",
            "user": f"U{i}",
            "text": f"테스트 메시지 {i}번 - " + "내용 " * 20,
        })
    store.append_thread_message(channel_id, "1000.000", {
        "ts": "1000.001",
        "user": "U99",
        "text": "스레드 답글",
    })


class FakeObserver:
    """ChannelObserver mock"""

    def __init__(self, result: ChannelObserverResult | None = None):
        self.result = result or ChannelObserverResult(
            digest="새로운 digest 결과",
            importance=4,
            reaction_type="none",
        )
        self.call_count = 0

    async def observe(self, **kwargs) -> ChannelObserverResult | None:
        self.call_count += 1
        return self.result


class FakeCompressor:
    """DigestCompressor mock"""

    def __init__(self, result: DigestCompressorResult | None = None):
        self.result = result or DigestCompressorResult(
            digest="압축된 digest",
            token_count=100,
        )
        self.call_count = 0

    async def compress(self, **kwargs) -> DigestCompressorResult | None:
        self.call_count += 1
        return self.result


class TestDigestChannel:
    """소화 파이프라인 통합 테스트"""

    @pytest.mark.asyncio
    async def test_skip_when_buffer_below_threshold(self, store, channel_id):
        """버퍼 토큰이 임계치 미만이면 스킵"""
        store.append_channel_message(channel_id, {
            "ts": "1.1", "user": "U1", "text": "짧은 메시지",
        })
        observer = FakeObserver()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=99999,
        )

        assert result is None
        assert observer.call_count == 0
        # 버퍼는 그대로 유지
        assert len(store.load_channel_buffer(channel_id)) == 1

    @pytest.mark.asyncio
    async def test_digest_success(self, store, channel_id):
        """정상 소화: Observer 호출 → digest 저장 → 버퍼 비우기"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,  # 낮은 임계치로 즉시 트리거
        )

        assert result is not None
        assert result.digest == "새로운 digest 결과"
        assert result.importance == 4
        assert observer.call_count == 1

        # digest가 저장되었는지 확인
        saved = store.get_digest(channel_id)
        assert saved is not None
        assert saved["content"] == "새로운 digest 결과"

        # 버퍼가 비워졌는지 확인
        assert len(store.load_channel_buffer(channel_id)) == 0
        assert len(store.load_all_thread_buffers(channel_id)) == 0

    @pytest.mark.asyncio
    async def test_digest_with_existing_digest(self, store, channel_id):
        """기존 digest가 있을 때 Observer에 전달되는지 확인"""
        store.save_digest(channel_id, "이전 digest", {"token_count": 50})
        _fill_buffer(store, channel_id)

        observer = FakeObserver()
        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        assert result is not None
        assert observer.call_count == 1

    @pytest.mark.asyncio
    async def test_digest_triggers_compressor(self, store, channel_id):
        """digest 토큰이 임계치 초과하면 Compressor 호출"""
        _fill_buffer(store, channel_id)

        long_digest = "장문의 digest " * 500
        observer = FakeObserver(ChannelObserverResult(
            digest=long_digest,
            importance=3,
            reaction_type="none",
        ))
        compressor = FakeCompressor()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
            compressor=compressor,
            digest_max_tokens=10,  # 매우 낮은 임계치
            digest_target_tokens=5,
        )

        assert result is not None
        assert compressor.call_count == 1
        # 압축된 digest가 저장됨
        saved = store.get_digest(channel_id)
        assert saved["content"] == "압축된 digest"

    @pytest.mark.asyncio
    async def test_digest_no_compressor_when_under_threshold(self, store, channel_id):
        """digest 토큰이 임계치 이하면 Compressor 호출 안 함"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver()
        compressor = FakeCompressor()

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
            compressor=compressor,
            digest_max_tokens=999999,
        )

        assert result is not None
        assert compressor.call_count == 0

    @pytest.mark.asyncio
    async def test_observer_returns_none(self, store, channel_id):
        """Observer가 None을 반환하면 파이프라인도 None"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver(result=None)
        observer.result = None  # 명시적 None 설정

        class NoneObserver:
            call_count = 0
            async def observe(self, **kwargs):
                self.call_count += 1
                return None

        none_observer = NoneObserver()
        result = await digest_channel(
            store=store,
            observer=none_observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        assert result is None
        # 버퍼는 비우지 않음 (실패했으므로)
        assert len(store.load_channel_buffer(channel_id)) > 0

    @pytest.mark.asyncio
    async def test_reaction_returned(self, store, channel_id):
        """반응 정보가 결과에 포함되는지 확인"""
        _fill_buffer(store, channel_id)

        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 결과",
            importance=7,
            reaction_type="react",
            reaction_target="1001.000",
            reaction_content="laughing",
        ))

        result = await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        assert result is not None
        assert result.reaction_type == "react"
        assert result.reaction_target == "1001.000"
        assert result.reaction_content == "laughing"

    @pytest.mark.asyncio
    async def test_meta_updated(self, store, channel_id):
        """digest meta에 토큰 수와 중요도가 기록되는지"""
        _fill_buffer(store, channel_id)
        observer = FakeObserver(ChannelObserverResult(
            digest="관찰 내용",
            importance=6,
            reaction_type="none",
        ))

        await digest_channel(
            store=store,
            observer=observer,
            channel_id=channel_id,
            buffer_threshold=1,
        )

        saved = store.get_digest(channel_id)
        meta = saved["meta"]
        assert "token_count" in meta
        assert "last_importance" in meta
        assert meta["last_importance"] == 6
