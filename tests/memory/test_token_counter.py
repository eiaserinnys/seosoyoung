"""토큰 카운터 단위 테스트"""

import pytest

from seosoyoung.slackbot.plugins.memory.token_counter import TokenCounter


@pytest.fixture
def counter():
    return TokenCounter()


class TestCountString:
    def test_empty_string(self, counter):
        assert counter.count_string("") == 0

    def test_none_equivalent_empty(self, counter):
        """빈 문자열은 0을 반환"""
        assert counter.count_string("") == 0

    def test_english_text(self, counter):
        result = counter.count_string("Hello, world!")
        assert result > 0
        assert isinstance(result, int)

    def test_korean_text(self, counter):
        result = counter.count_string("안녕하세요, 서소영입니다.")
        assert result > 0

    def test_mixed_language(self, counter):
        result = counter.count_string("서소영이 eb_lore의 glossary를 업데이트했습니다.")
        assert result > 0

    def test_longer_text_has_more_tokens(self, counter):
        short = counter.count_string("hello")
        long = counter.count_string("hello world this is a longer text for testing")
        assert long > short


class TestCountMessages:
    def test_empty_messages(self, counter):
        assert counter.count_messages([]) == 0

    def test_single_message(self, counter):
        messages = [{"role": "user", "content": "hello"}]
        result = counter.count_messages(messages)
        # role + content + TOKENS_PER_MESSAGE overhead
        assert result > TokenCounter.TOKENS_PER_MESSAGE

    def test_multiple_messages(self, counter):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        single = counter.count_messages(messages[:1])
        double = counter.count_messages(messages)
        assert double > single

    def test_message_overhead(self, counter):
        """각 메시지에 TOKENS_PER_MESSAGE 오버헤드가 추가되는지 확인"""
        # 빈 content의 메시지도 오버헤드가 있어야 함
        messages = [{"role": "user", "content": ""}]
        result = counter.count_messages(messages)
        # role("user") 토큰 + 오버헤드
        assert result >= TokenCounter.TOKENS_PER_MESSAGE

    def test_missing_fields(self, counter):
        """role이나 content 필드가 없는 메시지도 처리"""
        messages = [{"role": "user"}, {"content": "hello"}, {}]
        result = counter.count_messages(messages)
        assert result > 0
