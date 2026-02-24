"""문장 분할기 테스트."""

import pytest
from seosoyoung.search.sentence_splitter import split_sentences


class TestSplitSentences:
    """split_sentences 함수 테스트."""

    def test_split_by_period(self):
        text = "첫 번째 문장이다. 두 번째 문장이다."
        result = split_sentences(text)
        assert result == ["첫 번째 문장이다.", "두 번째 문장이다."]

    def test_split_by_question_mark(self):
        text = "무엇을 할 건가? 아무것도 하지 않겠다."
        result = split_sentences(text)
        assert result == ["무엇을 할 건가?", "아무것도 하지 않겠다."]

    def test_split_by_exclamation(self):
        text = "가자! 서둘러야 해."
        result = split_sentences(text)
        assert result == ["가자!", "서둘러야 해."]

    def test_split_by_ellipsis(self):
        text = "그건... 말하기 어렵다."
        result = split_sentences(text)
        assert result == ["그건...", "말하기 어렵다."]

    def test_split_english(self):
        text = "Let's go. We don't have time."
        result = split_sentences(text)
        assert result == ["Let's go.", "We don't have time."]

    def test_linebreak_to_space(self):
        text = "첫 번째 줄.\n두 번째 줄."
        result = split_sentences(text)
        assert result == ["첫 번째 줄.", "두 번째 줄."]

    def test_multiple_whitespace_collapse(self):
        text = "여기에  공백이   많다.   정리해야 한다."
        result = split_sentences(text)
        assert result == ["여기에 공백이 많다.", "정리해야 한다."]

    def test_trim_and_empty_filter(self):
        text = "  문장이다.   "
        result = split_sentences(text)
        assert result == ["문장이다."]

    def test_min_length_filter(self):
        text = "a. 긴 문장이 여기 있다."
        result = split_sentences(text, min_length=3)
        assert result == ["긴 문장이 여기 있다."]

    def test_empty_input(self):
        assert split_sentences("") == []
        assert split_sentences("   ") == []

    def test_no_punctuation(self):
        text = "구두점 없는 텍스트"
        result = split_sentences(text)
        assert result == ["구두점 없는 텍스트"]

    def test_korean_period(self):
        text = "일본어 마침표。다음 문장이다."
        result = split_sentences(text)
        assert result == ["일본어 마침표。", "다음 문장이다."]

    def test_mixed_punctuation(self):
        text = "정말? 그렇구나! 알겠다... 가자."
        result = split_sentences(text)
        assert result == ["정말?", "그렇구나!", "알겠다...", "가자."]

    def test_multiline_paragraph(self):
        text = """악마를 사냥하는 건 내 전문이야.
하지만 이번엔 다르다.
그놈은... 보통이 아니었어."""
        result = split_sentences(text)
        assert result == [
            "악마를 사냥하는 건 내 전문이야.",
            "하지만 이번엔 다르다.",
            "그놈은...",
            "보통이 아니었어.",
        ]

    def test_consecutive_ellipsis_and_text(self):
        text = "그런데... 어쩌면..."
        result = split_sentences(text)
        assert result == ["그런데...", "어쩌면..."]
