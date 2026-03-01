"""트리거 워드 감지 테스트

_contains_trigger_word는 ChannelObserverPlugin의 내부 메서드로 이동되었습니다.
이 테스트는 플러그인 인스턴스를 직접 생성하여 검증합니다.
"""

import pytest

from seosoyoung.slackbot.plugins.channel_observer.plugin import (
    ChannelObserverPlugin,
)


@pytest.fixture()
async def plugin_with_triggers():
    """트리거 워드가 설정된 ChannelObserverPlugin 인스턴스."""
    p = ChannelObserverPlugin()
    await p.on_load({
        "memory_path": "/tmp/test",
        "trigger_words": ["소영", "서소영", "soyoung", "SeoSoyoung"],
    })
    return p


@pytest.fixture()
async def plugin_no_triggers():
    """트리거 워드가 없는 ChannelObserverPlugin 인스턴스."""
    p = ChannelObserverPlugin()
    await p.on_load({
        "memory_path": "/tmp/test",
        "trigger_words": [],
    })
    return p


class TestContainsTriggerWord:
    """ChannelObserverPlugin._contains_trigger_word 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_no_trigger_words_configured(self, plugin_no_triggers):
        """트리거 워드가 설정되지 않으면 항상 False"""
        assert plugin_no_triggers._contains_trigger_word("소영아 안녕") is False

    @pytest.mark.asyncio
    async def test_match_exact(self, plugin_with_triggers):
        """정확히 일치하는 트리거 워드 감지"""
        assert plugin_with_triggers._contains_trigger_word("소영") is True

    @pytest.mark.asyncio
    async def test_match_substring(self, plugin_with_triggers):
        """문장 내에 포함된 트리거 워드 감지"""
        assert plugin_with_triggers._contains_trigger_word("소영아 이것 좀 봐줘") is True

    @pytest.mark.asyncio
    async def test_no_match(self, plugin_with_triggers):
        """트리거 워드가 없는 텍스트"""
        assert plugin_with_triggers._contains_trigger_word("오늘 날씨가 좋다") is False

    @pytest.mark.asyncio
    async def test_case_insensitive(self, plugin_with_triggers):
        """대소문자 무시 매칭"""
        assert plugin_with_triggers._contains_trigger_word("seosoyoung is here") is True

    @pytest.mark.asyncio
    async def test_multiple_trigger_words(self, plugin_with_triggers):
        """여러 트리거 워드 중 하나라도 매칭"""
        assert plugin_with_triggers._contains_trigger_word("서소영 봇") is True
        assert plugin_with_triggers._contains_trigger_word("안녕 소영") is True
        assert plugin_with_triggers._contains_trigger_word("hey soyoung") is True
        assert plugin_with_triggers._contains_trigger_word("아무 관련 없는 말") is False

    @pytest.mark.asyncio
    async def test_empty_text(self, plugin_with_triggers):
        """빈 텍스트"""
        assert plugin_with_triggers._contains_trigger_word("") is False
