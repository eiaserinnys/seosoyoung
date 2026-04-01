"""build_request() 프롬프트 구성 테스트"""

import pytest

from seosoyoung.slackbot.handlers.mention import build_request


class TestBuildRequest:
    """build_request() 반환값 구조 테스트"""

    def test_returns_tuple(self):
        """build_request는 (prompt, context_items) 튜플을 반환"""
        result = build_request(
            context="대화 기록",
            question="이 코드 분석해줘",
            file_context="",
            slack_context="channel_id: C123",
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_prompt_is_question(self):
        """prompt에 사용자 질문이 그대로 담김"""
        prompt, _ = build_request(
            context="",
            question="안녕하세요",
            file_context="",
            slack_context="",
        )
        assert prompt == "안녕하세요"

    def test_context_items_include_slack_metadata(self):
        """context_items에 slack_metadata 항목이 포함"""
        _, context_items = build_request(
            context="",
            question="질문",
            file_context="",
            slack_context="channel_id: C123",
        )
        keys = {item["key"] for item in context_items}
        assert "slack_metadata" in keys

    def test_context_items_include_channel_history(self):
        """context_items에 channel_history 항목이 포함"""
        _, context_items = build_request(
            context="채널 히스토리",
            question="요약해줘",
            file_context="",
            slack_context="",
        )
        keys = {item["key"] for item in context_items}
        assert "channel_history" in keys

    def test_file_context_adds_attachments(self):
        """file_context가 있으면 context_items에 attachments 항목 추가"""
        _, context_items = build_request(
            context="",
            question="파일 분석해줘",
            file_context="[파일: test.py, 타입: text, 크기: 100B]",
            slack_context="",
        )
        keys = {item["key"] for item in context_items}
        assert "attachments" in keys

    def test_no_file_context_no_attachments(self):
        """file_context가 없으면 attachments 항목 생략"""
        _, context_items = build_request(
            context="",
            question="질문입니다",
            file_context="",
            slack_context="",
        )
        keys = {item["key"] for item in context_items}
        assert "attachments" not in keys

    def test_channel_history_content_preserved(self):
        """channel_history 항목에 전달한 context가 그대로 담김"""
        history = "채널 기록 내용"
        _, context_items = build_request(
            context=history,
            question="요약해줘",
            file_context="",
            slack_context="",
        )
        history_item = next(i for i in context_items if i["key"] == "channel_history")
        assert history in history_item["content"]

    def test_empty_question_prompt_is_empty(self):
        """질문이 비어있으면 prompt도 빈 문자열"""
        prompt, _ = build_request(
            context="기록",
            question="",
            file_context="파일 정보",
            slack_context="",
        )
        assert prompt == ""

    def test_context_items_have_required_keys(self):
        """context_items의 각 항목은 key, label, content 필드를 가짐"""
        _, context_items = build_request(
            context="기록",
            question="질문",
            file_context="파일",
            slack_context="메타데이터",
        )
        for item in context_items:
            assert "key" in item
            assert "label" in item
            assert "content" in item
