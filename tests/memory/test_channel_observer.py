"""ChannelObserver + DigestCompressor 단위 테스트"""

import pytest

from seosoyoung.memory.channel_observer import (
    ChannelObserver,
    ChannelObserverResult,
    DigestCompressor,
    DigestCompressorResult,
    DigestResult,
    JudgeItem,
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
        assert result.reasoning is None

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
        assert result.reasoning is None

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
        assert result.reasoning is None

    def test_parse_fallback(self):
        result = parse_judge_output("뭔가 이상한 응답")
        assert result.importance == 0
        assert result.reaction_type == "none"
        assert result.reasoning is None

    def test_parse_reasoning(self):
        """reasoning 태그가 있으면 파싱"""
        text = (
            '<reasoning>서소영이 직접 언급되어 중요도 높음</reasoning>\n'
            '<importance>7</importance>\n'
            '<reaction type="react">\n'
            '<react target="111.222" emoji="eyes" />\n'
            '</reaction>'
        )
        result = parse_judge_output(text)
        assert result.reasoning == "서소영이 직접 언급되어 중요도 높음"
        assert result.importance == 7
        assert result.reaction_type == "react"
        assert result.reaction_target == "111.222"
        assert result.reaction_content == "eyes"

    def test_parse_reasoning_with_intervene(self):
        """intervene과 함께 reasoning 파싱"""
        text = (
            '<reasoning>EB 프로젝트 관련 흥미로운 논의가 진행 중</reasoning>\n'
            '<importance>8</importance>\n'
            '<reaction type="intervene">\n'
            '<intervene target="channel">그 이야기, 저도 한마디 보태겠습니다.</intervene>\n'
            '</reaction>'
        )
        result = parse_judge_output(text)
        assert result.reasoning == "EB 프로젝트 관련 흥미로운 논의가 진행 중"
        assert result.importance == 8
        assert result.reaction_type == "intervene"
        assert result.reaction_content == "그 이야기, 저도 한마디 보태겠습니다."


# ── parse_judge_output 복수 판단 ────────────────────────

class TestParseJudgeOutputMulti:
    """복수 <judgment> 블록 파싱 테스트"""

    def test_parse_multi_judgments(self):
        """여러 judgment 블록 파싱"""
        text = (
            '<judgments>\n'
            '<judgment ts="111.222">\n'
            '<reasoning>재미있는 대화</reasoning>\n'
            '<emotion>웃음이 나온다</emotion>\n'
            '<importance>5</importance>\n'
            '<reaction type="react">\n'
            '<react target="111.222" emoji="laughing" />\n'
            '</reaction>\n'
            '</judgment>\n'
            '<judgment ts="333.444">\n'
            '<reasoning>별 일 없음</reasoning>\n'
            '<emotion>평온하다</emotion>\n'
            '<importance>1</importance>\n'
            '<reaction type="none" />\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert isinstance(result, JudgeResult)
        assert len(result.items) == 2

        item0 = result.items[0]
        assert isinstance(item0, JudgeItem)
        assert item0.ts == "111.222"
        assert item0.importance == 5
        assert item0.reaction_type == "react"
        assert item0.reaction_target == "111.222"
        assert item0.reaction_content == "laughing"
        assert item0.reasoning == "재미있는 대화"
        assert item0.emotion == "웃음이 나온다"

        item1 = result.items[1]
        assert item1.ts == "333.444"
        assert item1.importance == 1
        assert item1.reaction_type == "none"

    def test_parse_multi_with_intervene(self):
        """react와 intervene이 섞인 복수 판단"""
        text = (
            '<judgments>\n'
            '<judgment ts="100.000">\n'
            '<reasoning>EB 프로젝트 이야기</reasoning>\n'
            '<emotion>관심이 간다</emotion>\n'
            '<importance>6</importance>\n'
            '<reaction type="react">\n'
            '<react target="100.000" emoji="eyes" />\n'
            '</reaction>\n'
            '</judgment>\n'
            '<judgment ts="200.000">\n'
            '<reasoning>서소영이 직접 언급됨</reasoning>\n'
            '<emotion>호출받은 느낌이다</emotion>\n'
            '<importance>9</importance>\n'
            '<reaction type="intervene">\n'
            '<intervene target="channel">부르셨습니까?</intervene>\n'
            '</reaction>\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert len(result.items) == 2
        assert result.items[0].reaction_type == "react"
        assert result.items[1].reaction_type == "intervene"
        assert result.items[1].reaction_content == "부르셨습니까?"

    def test_parse_single_judgment_block(self):
        """judgment 블록이 1개만 있는 경우"""
        text = (
            '<judgments>\n'
            '<judgment ts="500.000">\n'
            '<importance>3</importance>\n'
            '<reaction type="none" />\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert len(result.items) == 1
        assert result.items[0].ts == "500.000"
        assert result.items[0].importance == 3
        assert result.items[0].reaction_type == "none"

    def test_backward_compat_no_judgment_blocks(self):
        """judgment 블록이 없으면 하위호환 단일 파싱"""
        text = (
            '<importance>4</importance>\n'
            '<reaction type="none" />'
        )
        result = parse_judge_output(text)
        assert result.items == []
        assert result.importance == 4
        assert result.reaction_type == "none"

    def test_parse_multi_with_addressed_and_instruction(self):
        """addressed_to_me, is_instruction 필드가 포함된 복수 판단 파싱"""
        text = (
            '<judgments>\n'
            '<judgment ts="111.222">\n'
            '<addressed_to_me>yes</addressed_to_me>\n'
            '<addressed_to_me_reason>서소영을 직접 멘션함</addressed_to_me_reason>\n'
            '<is_instruction>yes</is_instruction>\n'
            '<is_instruction_reason>번역 작업을 요청함</is_instruction_reason>\n'
            '<emotion>호출받았다</emotion>\n'
            '<importance>8</importance>\n'
            '<reaction type="intervene">\n'
            '<intervene target="channel">알겠습니다.</intervene>\n'
            '</reaction>\n'
            '<reasoning>서소영에게 직접 번역을 요청함</reasoning>\n'
            '</judgment>\n'
            '<judgment ts="333.444">\n'
            '<addressed_to_me>no</addressed_to_me>\n'
            '<addressed_to_me_reason>일반 대화임</addressed_to_me_reason>\n'
            '<is_instruction>no</is_instruction>\n'
            '<is_instruction_reason>정보 공유일 뿐</is_instruction_reason>\n'
            '<emotion>평온하다</emotion>\n'
            '<importance>2</importance>\n'
            '<reaction type="none" />\n'
            '<reasoning>별다른 반응이 필요 없음</reasoning>\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert len(result.items) == 2

        item0 = result.items[0]
        assert item0.addressed_to_me is True
        assert item0.addressed_to_me_reason == "서소영을 직접 멘션함"
        assert item0.is_instruction is True
        assert item0.is_instruction_reason == "번역 작업을 요청함"
        assert item0.importance == 8
        assert item0.reaction_type == "intervene"

        item1 = result.items[1]
        assert item1.addressed_to_me is False
        assert item1.addressed_to_me_reason == "일반 대화임"
        assert item1.is_instruction is False
        assert item1.is_instruction_reason == "정보 공유일 뿐"
        assert item1.importance == 2
        assert item1.reaction_type == "none"

    def test_backward_compat_no_addressed_instruction_fields(self):
        """새 필드가 없는 기존 형식 응답도 정상 파싱 (하위호환)"""
        text = (
            '<judgments>\n'
            '<judgment ts="500.000">\n'
            '<reasoning>별 일 없음</reasoning>\n'
            '<emotion>평온</emotion>\n'
            '<importance>3</importance>\n'
            '<reaction type="none" />\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert len(result.items) == 1
        item = result.items[0]
        assert item.addressed_to_me is False
        assert item.addressed_to_me_reason is None
        assert item.is_instruction is False
        assert item.is_instruction_reason is None
        assert item.importance == 3

    def test_backward_compat_single_with_new_fields(self):
        """judgment 블록 없이 단일 파싱에서도 새 필드 파싱"""
        text = (
            '<addressed_to_me>yes</addressed_to_me>\n'
            '<addressed_to_me_reason>이름 호출</addressed_to_me_reason>\n'
            '<is_instruction>no</is_instruction>\n'
            '<is_instruction_reason>질문일 뿐</is_instruction_reason>\n'
            '<importance>5</importance>\n'
            '<reaction type="react">\n'
            '<react target="1.1" emoji="eyes" />\n'
            '</reaction>'
        )
        result = parse_judge_output(text)
        assert result.items == []
        assert result.addressed_to_me is True
        assert result.addressed_to_me_reason == "이름 호출"
        assert result.is_instruction is False
        assert result.is_instruction_reason == "질문일 뿐"

    def test_parse_multi_with_context_meaning_and_related(self):
        """context_meaning, related_to_me 필드가 포함된 복수 판단 파싱"""
        text = (
            '<judgments>\n'
            '<judgment ts="111.222">\n'
            '<context_meaning>EB 프로젝트의 아리엘라 캐릭터에 대한 논의 중</context_meaning>\n'
            '<addressed_to_me>no</addressed_to_me>\n'
            '<addressed_to_me_reason>일반 대화임</addressed_to_me_reason>\n'
            '<related_to_me>yes</related_to_me>\n'
            '<related_to_me_reason>서소영의 이전 발언이 언급됨</related_to_me_reason>\n'
            '<is_instruction>no</is_instruction>\n'
            '<is_instruction_reason>정보 공유임</is_instruction_reason>\n'
            '<emotion>관심이 간다</emotion>\n'
            '<importance>5</importance>\n'
            '<reaction type="react">\n'
            '<react target="111.222" emoji="eyes" />\n'
            '</reaction>\n'
            '<reasoning>EB 프로젝트 관련 흥미로운 논의</reasoning>\n'
            '</judgment>\n'
            '<judgment ts="333.444">\n'
            '<context_meaning>팀원이 점심 메뉴를 물어보는 일상 대화</context_meaning>\n'
            '<addressed_to_me>no</addressed_to_me>\n'
            '<addressed_to_me_reason>일반 질문임</addressed_to_me_reason>\n'
            '<related_to_me>no</related_to_me>\n'
            '<related_to_me_reason>서소영과 무관한 대화</related_to_me_reason>\n'
            '<is_instruction>no</is_instruction>\n'
            '<is_instruction_reason>정보 요청일 뿐</is_instruction_reason>\n'
            '<emotion>평온하다</emotion>\n'
            '<importance>1</importance>\n'
            '<reaction type="none" />\n'
            '<reasoning>별다른 반응 불필요</reasoning>\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert len(result.items) == 2

        item0 = result.items[0]
        assert item0.context_meaning == "EB 프로젝트의 아리엘라 캐릭터에 대한 논의 중"
        assert item0.related_to_me is True
        assert item0.related_to_me_reason == "서소영의 이전 발언이 언급됨"
        assert item0.addressed_to_me is False
        assert item0.importance == 5

        item1 = result.items[1]
        assert item1.context_meaning == "팀원이 점심 메뉴를 물어보는 일상 대화"
        assert item1.related_to_me is False
        assert item1.related_to_me_reason == "서소영과 무관한 대화"
        assert item1.importance == 1

    def test_backward_compat_no_context_meaning_related(self):
        """context_meaning, related_to_me 없는 기존 형식도 정상 파싱"""
        text = (
            '<judgments>\n'
            '<judgment ts="500.000">\n'
            '<reasoning>별 일 없음</reasoning>\n'
            '<emotion>평온</emotion>\n'
            '<importance>3</importance>\n'
            '<reaction type="none" />\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        item = result.items[0]
        assert item.context_meaning is None
        assert item.related_to_me is False
        assert item.related_to_me_reason is None

    def test_parse_multi_with_linked_conversation(self):
        """linked_message_ts, link_reason 필드가 포함된 복수 판단 파싱"""
        text = (
            '<judgments>\n'
            '<judgment ts="111.222">\n'
            '<linked_conversation>\n'
            '<linked_message_ts>100.000</linked_message_ts>\n'
            '<link_reason>이전 메시지에 대한 답변</link_reason>\n'
            '</linked_conversation>\n'
            '<context_meaning>이전 논의를 이어가는 대화</context_meaning>\n'
            '<addressed_to_me>no</addressed_to_me>\n'
            '<addressed_to_me_reason>일반 대화</addressed_to_me_reason>\n'
            '<related_to_me>no</related_to_me>\n'
            '<related_to_me_reason>무관</related_to_me_reason>\n'
            '<is_instruction>no</is_instruction>\n'
            '<is_instruction_reason>대화일 뿐</is_instruction_reason>\n'
            '<emotion>평온하다</emotion>\n'
            '<importance>3</importance>\n'
            '<reaction type="none" />\n'
            '<reasoning>이어지는 대화이나 반응 불필요</reasoning>\n'
            '</judgment>\n'
            '<judgment ts="222.333">\n'
            '<context_meaning>독립적인 새 화제</context_meaning>\n'
            '<addressed_to_me>no</addressed_to_me>\n'
            '<addressed_to_me_reason>일반 대화</addressed_to_me_reason>\n'
            '<related_to_me>no</related_to_me>\n'
            '<related_to_me_reason>무관</related_to_me_reason>\n'
            '<is_instruction>no</is_instruction>\n'
            '<is_instruction_reason>대화일 뿐</is_instruction_reason>\n'
            '<emotion>평온하다</emotion>\n'
            '<importance>1</importance>\n'
            '<reaction type="none" />\n'
            '<reasoning>별다른 반응 불필요</reasoning>\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        assert len(result.items) == 2

        item0 = result.items[0]
        assert item0.linked_message_ts == "100.000"
        assert item0.link_reason == "이전 메시지에 대한 답변"

        item1 = result.items[1]
        assert item1.linked_message_ts is None
        assert item1.link_reason is None

    def test_backward_compat_no_linked_conversation(self):
        """linked_conversation 없는 기존 형식도 정상 파싱"""
        text = (
            '<judgments>\n'
            '<judgment ts="500.000">\n'
            '<reasoning>별 일 없음</reasoning>\n'
            '<emotion>평온</emotion>\n'
            '<importance>3</importance>\n'
            '<reaction type="none" />\n'
            '</judgment>\n'
            '</judgments>'
        )
        result = parse_judge_output(text)
        item = result.items[0]
        assert item.linked_message_ts is None
        assert item.link_reason is None

    def test_backward_compat_single_with_context_meaning_related(self):
        """단일 파싱에서도 context_meaning, related_to_me 파싱"""
        text = (
            '<context_meaning>팀 회의 중 서소영 관련 언급</context_meaning>\n'
            '<related_to_me>yes</related_to_me>\n'
            '<related_to_me_reason>서소영의 작업이 언급됨</related_to_me_reason>\n'
            '<importance>5</importance>\n'
            '<reaction type="none" />'
        )
        result = parse_judge_output(text)
        assert result.items == []
        assert result.context_meaning == "팀 회의 중 서소영 관련 언급"
        assert result.related_to_me is True
        assert result.related_to_me_reason == "서소영의 작업이 언급됨"


# ── ChannelObserver.judge() 복수 판단 ─────────────────────

class TestChannelObserverJudgeMulti:
    """ChannelObserver.judge()가 복수 판단 응답을 반환하는 테스트"""

    @pytest.mark.asyncio
    async def test_judge_returns_multi_items(self):
        mock_text = (
            '<judgments>\n'
            '<judgment ts="1.1">\n'
            '<reasoning>test</reasoning>\n'
            '<importance>3</importance>\n'
            '<reaction type="react">\n'
            '<react target="1.1" emoji="eyes" />\n'
            '</reaction>\n'
            '</judgment>\n'
            '<judgment ts="2.2">\n'
            '<importance>1</importance>\n'
            '<reaction type="none" />\n'
            '</judgment>\n'
            '</judgments>'
        )
        observer = ChannelObserver(api_key="fake-key")
        observer.client = _make_mock_client(mock_text)

        result = await observer.judge(
            channel_id="C123",
            digest=None,
            judged_messages=[],
            pending_messages=[
                {"ts": "1.1", "user": "U1", "text": "hi"},
                {"ts": "2.2", "user": "U2", "text": "bye"},
            ],
        )

        assert result is not None
        assert len(result.items) == 2
        assert result.items[0].ts == "1.1"
        assert result.items[0].reaction_type == "react"
        assert result.items[1].ts == "2.2"
        assert result.items[1].reaction_type == "none"


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
        assert "[1.1] U1: hello" in prompt

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
        assert "[999.001] U2: reply" in prompt

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
        assert "[1.1] U1: hello" in user_prompt

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
        assert "[0.1] U1: old msg" in user_prompt
        assert "[1.1] U2: new msg" in user_prompt


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
