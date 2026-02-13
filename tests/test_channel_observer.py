"""ChannelObserver + DigestCompressor 단위 테스트"""

import pytest

from seosoyoung.memory.channel_observer import (
    ChannelObserver,
    ChannelObserverResult,
    DigestCompressor,
    DigestCompressorResult,
    DigestResult,
    JudgeResult,
    parse_channel_observer_output,
    parse_judge_output,
)


# ── parse_channel_observer_output ─────────────────────────

class TestParseChannelObserverOutput:
    """XML 응답 파싱 테스트"""

    def test_parse_full_none_reaction(self):
        text = (
            '<digest>오늘은 별일 없었다.</digest>\n'
            '<importance>2</importance>\n'
            '<reaction type="none" />'
        )
        result = parse_channel_observer_output(text)
        assert result.digest == "오늘은 별일 없었다."
        assert result.importance == 2
        assert result.reaction_type == "none"
        assert result.reaction_target is None
        assert result.reaction_content is None

    def test_parse_react_reaction(self):
        text = (
            '<digest>재미있는 대화가 오갔다.</digest>\n'
            '<importance>5</importance>\n'
            '<reaction type="react">\n'
            '<react target="1234567890.123" emoji="laughing" />\n'
            '</reaction>'
        )
        result = parse_channel_observer_output(text)
        assert result.digest == "재미있는 대화가 오갔다."
        assert result.importance == 5
        assert result.reaction_type == "react"
        assert result.reaction_target == "1234567890.123"
        assert result.reaction_content == "laughing"

    def test_parse_intervene_channel(self):
        text = (
            '<digest>서소영이 직접 언급되었다.</digest>\n'
            '<importance>8</importance>\n'
            '<reaction type="intervene">\n'
            '<intervene target="channel">아이고, 뭔 소동이란 말이오?</intervene>\n'
            '</reaction>'
        )
        result = parse_channel_observer_output(text)
        assert result.digest == "서소영이 직접 언급되었다."
        assert result.importance == 8
        assert result.reaction_type == "intervene"
        assert result.reaction_target == "channel"
        assert result.reaction_content == "아이고, 뭔 소동이란 말이오?"

    def test_parse_intervene_thread(self):
        text = (
            '<digest>스레드에서 흥미로운 논의.</digest>\n'
            '<importance>7</importance>\n'
            '<reaction type="intervene">\n'
            '<intervene target="thread:1234567890.123">그 이야기 자세히 해주시겠소?</intervene>\n'
            '</reaction>'
        )
        result = parse_channel_observer_output(text)
        assert result.reaction_type == "intervene"
        assert result.reaction_target == "thread:1234567890.123"
        assert result.reaction_content == "그 이야기 자세히 해주시겠소?"

    def test_parse_fallback_on_missing_tags(self):
        """태그가 없는 경우 전체 텍스트를 digest로 사용"""
        text = "그냥 평범한 텍스트"
        result = parse_channel_observer_output(text)
        assert result.digest == "그냥 평범한 텍스트"
        assert result.importance == 0
        assert result.reaction_type == "none"

    def test_parse_importance_clamp(self):
        """importance가 범위를 벗어나면 클램핑"""
        text = (
            '<digest>test</digest>\n'
            '<importance>15</importance>\n'
            '<reaction type="none" />'
        )
        result = parse_channel_observer_output(text)
        assert result.importance == 10

        text2 = (
            '<digest>test</digest>\n'
            '<importance>-3</importance>\n'
            '<reaction type="none" />'
        )
        result2 = parse_channel_observer_output(text2)
        assert result2.importance == 0

    def test_parse_multiline_digest(self):
        text = (
            '<digest>\n'
            '## 오늘의 관찰\n'
            '- 재미있는 일이 있었다 [thread:123.456]\n'
            '- 누군가 봇을 놀렸다\n'
            '</digest>\n'
            '<importance>4</importance>\n'
            '<reaction type="none" />'
        )
        result = parse_channel_observer_output(text)
        assert "[thread:123.456]" in result.digest
        assert "오늘의 관찰" in result.digest


# ── ChannelObserver ───────────────────────────────────────

class TestChannelObserver:
    """ChannelObserver OpenAI mock 테스트"""

    @pytest.mark.asyncio
    async def test_observe_success(self):
        mock_response_text = (
            '<digest>새로운 관찰 결과</digest>\n'
            '<importance>5</importance>\n'
            '<reaction type="react">\n'
            '<react target="111.222" emoji="eyes" />\n'
            '</reaction>'
        )
        observer = ChannelObserver(api_key="fake-key", model="gpt-5-mini")
        observer.client = _make_mock_client(mock_response_text)

        result = await observer.observe(
            channel_id="C123",
            existing_digest=None,
            channel_messages=[{"ts": "111.222", "user": "U1", "text": "hello"}],
            thread_buffers={},
        )

        assert result is not None
        assert result.digest == "새로운 관찰 결과"
        assert result.importance == 5
        assert result.reaction_type == "react"
        assert result.reaction_target == "111.222"
        assert result.reaction_content == "eyes"

    @pytest.mark.asyncio
    async def test_observe_with_existing_digest(self):
        mock_response_text = (
            '<digest>기존 내용 + 새로운 관찰</digest>\n'
            '<importance>3</importance>\n'
            '<reaction type="none" />'
        )
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_mock_client(mock_response_text)

        result = await observer.observe(
            channel_id="C123",
            existing_digest="이전의 관찰 기록",
            channel_messages=[{"ts": "111.222", "user": "U1", "text": "hi"}],
            thread_buffers={"999.000": [{"ts": "999.001", "user": "U2", "text": "thread msg"}]},
        )

        assert result is not None
        assert "기존 내용" in result.digest

    @pytest.mark.asyncio
    async def test_observe_api_error(self):
        """API 호출 실패 시 None 반환"""
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_error_client(Exception("API error"))

        result = await observer.observe(
            channel_id="C123",
            existing_digest=None,
            channel_messages=[{"ts": "1.1", "user": "U1", "text": "msg"}],
            thread_buffers={},
        )
        assert result is None


# ── DigestCompressor ──────────────────────────────────────

class TestDigestCompressor:
    """DigestCompressor 단위 테스트"""

    @pytest.mark.asyncio
    async def test_compress_under_target(self):
        """1차 시도에서 목표 이하면 바로 반환"""
        mock_text = "<digest>압축된 내용</digest>"
        compressor = DigestCompressor(api_key="fake-key", model="gpt-5.2")
        compressor.client = _make_mock_client(mock_text)

        result = await compressor.compress(
            digest="매우 긴 기존 digest 내용...",
            target_tokens=5000,
        )

        assert result is not None
        assert result.digest == "압축된 내용"
        assert result.token_count > 0

    @pytest.mark.asyncio
    async def test_compress_retry_on_over_target(self):
        """1차가 목표 초과하면 2차 시도"""
        # 1차: 긴 텍스트, 2차: 짧은 텍스트
        call_count = 0

        class MockCompletions:
            async def create(self, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # 1차: 목표 토큰 초과하도록 긴 텍스트
                    return _mock_response(
                        "<digest>" + "가나다라마바사 " * 100 + "</digest>"
                    )
                else:
                    # 2차: 짧은 텍스트
                    return _mock_response("<digest>최종 압축</digest>")

        class MockChat:
            completions = MockCompletions()

        class MockClient:
            chat = MockChat()

        compressor = DigestCompressor(api_key="fake-key")
        compressor.client = MockClient()

        result = await compressor.compress(
            digest="원본 digest",
            target_tokens=10,  # 매우 낮은 목표로 설정하여 재시도 유도
        )

        assert result is not None
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_compress_api_error(self):
        compressor = DigestCompressor(api_key="fake-key")
        compressor.client = _make_error_client(Exception("API error"))

        result = await compressor.compress(
            digest="some digest",
            target_tokens=5000,
        )
        assert result is None


# ── parse_judge_output ────────────────────────────────────

class TestParseJudgeOutput:
    """Judge 응답 파싱 테스트"""

    def test_parse_none_reaction(self):
        text = (
            '<importance>2</importance>\n'
            '<reaction type="none" />'
        )
        result = parse_judge_output(text)
        assert isinstance(result, JudgeResult)
        assert result.importance == 2
        assert result.reaction_type == "none"
        assert result.reaction_target is None

    def test_parse_react(self):
        text = (
            '<importance>5</importance>\n'
            '<reaction type="react">\n'
            '<react target="111.222" emoji="laughing" />\n'
            '</reaction>'
        )
        result = parse_judge_output(text)
        assert result.importance == 5
        assert result.reaction_type == "react"
        assert result.reaction_target == "111.222"
        assert result.reaction_content == "laughing"

    def test_parse_intervene(self):
        text = (
            '<importance>8</importance>\n'
            '<reaction type="intervene">\n'
            '<intervene target="channel">한마디 하겠소.</intervene>\n'
            '</reaction>'
        )
        result = parse_judge_output(text)
        assert result.importance == 8
        assert result.reaction_type == "intervene"
        assert result.reaction_target == "channel"
        assert result.reaction_content == "한마디 하겠소."

    def test_parse_fallback(self):
        result = parse_judge_output("뭔가 이상한 응답")
        assert result.importance == 0
        assert result.reaction_type == "none"


# ── ChannelObserver.digest() ─────────────────────────────

class TestChannelObserverDigest:
    """ChannelObserver.digest() 단위 테스트"""

    @pytest.mark.asyncio
    async def test_digest_success(self):
        mock_text = "<digest>소화된 요약 내용</digest>"
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_mock_client(mock_text)

        result = await observer.digest(
            channel_id="C123",
            existing_digest=None,
            judged_messages=[{"ts": "1.1", "user": "U1", "text": "hello"}],
        )

        assert result is not None
        assert isinstance(result, DigestResult)
        assert result.digest == "소화된 요약 내용"
        assert result.token_count > 0

    @pytest.mark.asyncio
    async def test_digest_with_existing(self):
        mock_text = "<digest>기존 + 새 내용</digest>"
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_mock_client(mock_text)

        result = await observer.digest(
            channel_id="C123",
            existing_digest="기존 요약",
            judged_messages=[{"ts": "2.2", "user": "U1", "text": "new msg"}],
        )

        assert result is not None
        assert "기존 + 새 내용" in result.digest

    @pytest.mark.asyncio
    async def test_digest_api_error(self):
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_error_client(Exception("API error"))

        result = await observer.digest(
            channel_id="C123",
            existing_digest=None,
            judged_messages=[{"ts": "1.1", "user": "U1", "text": "msg"}],
        )
        assert result is None


# ── ChannelObserver.judge() ──────────────────────────────

class TestChannelObserverJudge:
    """ChannelObserver.judge() 단위 테스트"""

    @pytest.mark.asyncio
    async def test_judge_success(self):
        mock_text = (
            '<importance>6</importance>\n'
            '<reaction type="react">\n'
            '<react target="111.222" emoji="eyes" />\n'
            '</reaction>'
        )
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_mock_client(mock_text)

        result = await observer.judge(
            channel_id="C123",
            digest="채널 요약",
            judged_messages=[{"ts": "0.1", "user": "U1", "text": "old"}],
            pending_messages=[{"ts": "111.222", "user": "U2", "text": "new msg"}],
        )

        assert result is not None
        assert isinstance(result, JudgeResult)
        assert result.importance == 6
        assert result.reaction_type == "react"
        assert result.reaction_target == "111.222"
        assert result.reaction_content == "eyes"

    @pytest.mark.asyncio
    async def test_judge_none(self):
        mock_text = (
            '<importance>1</importance>\n'
            '<reaction type="none" />'
        )
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_mock_client(mock_text)

        result = await observer.judge(
            channel_id="C123",
            digest=None,
            judged_messages=[],
            pending_messages=[{"ts": "1.1", "user": "U1", "text": "hi"}],
        )

        assert result is not None
        assert result.reaction_type == "none"

    @pytest.mark.asyncio
    async def test_judge_api_error(self):
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_error_client(Exception("API error"))

        result = await observer.judge(
            channel_id="C123",
            digest=None,
            judged_messages=[],
            pending_messages=[{"ts": "1.1", "user": "U1", "text": "msg"}],
        )
        assert result is None


# ── 프롬프트 빌더 테스트 ──────────────────────────────────

class TestChannelPrompts:
    """channel_prompts 빌더 함수 테스트"""

    def test_build_user_prompt_no_existing(self):
        from seosoyoung.memory.channel_prompts import build_channel_observer_user_prompt
        from datetime import datetime, timezone

        prompt = build_channel_observer_user_prompt(
            channel_id="C123",
            existing_digest=None,
            channel_messages=[{"ts": "1.1", "user": "U1", "text": "hello"}],
            thread_buffers={},
            current_time=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        )

        assert "C123" in prompt
        assert "first observation" in prompt
        assert "[1.1] <U1>: hello" in prompt

    def test_build_user_prompt_with_existing(self):
        from seosoyoung.memory.channel_prompts import build_channel_observer_user_prompt

        prompt = build_channel_observer_user_prompt(
            channel_id="C456",
            existing_digest="기존 digest 내용",
            channel_messages=[],
            thread_buffers={"999.000": [{"ts": "999.001", "user": "U2", "text": "reply"}]},
        )

        assert "기존 digest 내용" in prompt
        assert "thread:999.000" in prompt
        assert "[999.001] <U2>: reply" in prompt

    def test_build_compressor_prompts(self):
        from seosoyoung.memory.channel_prompts import (
            build_digest_compressor_system_prompt,
            build_digest_compressor_retry_prompt,
        )

        sys_prompt = build_digest_compressor_system_prompt(5000)
        assert "5000" in sys_prompt

        retry = build_digest_compressor_retry_prompt(8000, 5000)
        assert "8000" in retry
        assert "5000" in retry

    def test_build_digest_only_prompts(self):
        from seosoyoung.memory.channel_prompts import (
            build_digest_only_system_prompt,
            build_digest_only_user_prompt,
        )
        from datetime import datetime, timezone

        sys_prompt = build_digest_only_system_prompt()
        assert "digest" in sys_prompt.lower()
        assert "reaction" not in sys_prompt.lower() or "NOT" in sys_prompt

        user_prompt = build_digest_only_user_prompt(
            channel_id="C123",
            existing_digest="기존 요약",
            judged_messages=[{"ts": "1.1", "user": "U1", "text": "hello"}],
            current_time=datetime(2025, 6, 1, 12, 0, tzinfo=timezone.utc),
        )
        assert "C123" in user_prompt
        assert "기존 요약" in user_prompt
        assert "[1.1] <U1>: hello" in user_prompt

    def test_build_judge_prompts(self):
        from seosoyoung.memory.channel_prompts import (
            build_judge_system_prompt,
            build_judge_user_prompt,
        )

        sys_prompt = build_judge_system_prompt()
        assert "reaction" in sys_prompt.lower() or "judge" in sys_prompt.lower()

        user_prompt = build_judge_user_prompt(
            channel_id="C456",
            digest="채널 요약 내용",
            judged_messages=[{"ts": "0.1", "user": "U1", "text": "old msg"}],
            pending_messages=[{"ts": "1.1", "user": "U2", "text": "new msg"}],
        )
        assert "C456" in user_prompt
        assert "채널 요약 내용" in user_prompt
        assert "[0.1] <U1>: old msg" in user_prompt
        assert "[1.1] <U2>: new msg" in user_prompt


# ── 헬퍼 ─────────────────────────────────────────────────

def _mock_response(content: str):
    """OpenAI chat.completions.create 응답 mock"""

    class Choice:
        def __init__(self):
            self.message = type("Message", (), {"content": content})()

    class Response:
        def __init__(self):
            self.choices = [Choice()]

    return Response()


def _make_mock_client(response_text: str):
    """정상 응답을 반환하는 mock OpenAI 클라이언트"""

    class MockCompletions:
        async def create(self, **kwargs):
            return _mock_response(response_text)

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()

    return MockClient()


def _make_error_client(error: Exception):
    """에러를 발생시키는 mock OpenAI 클라이언트"""

    class MockCompletions:
        async def create(self, **kwargs):
            raise error

    class MockChat:
        completions = MockCompletions()

    class MockClient:
        chat = MockChat()

    return MockClient()
