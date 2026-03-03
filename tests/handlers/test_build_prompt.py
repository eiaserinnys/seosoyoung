"""build_prompt() 프롬프트 구성 테스트"""

import pytest

from seosoyoung.slackbot.handlers.mention import build_prompt


class TestBuildPrompt:
    """build_prompt() XML 구조 프롬프트 테스트"""

    def test_basic_prompt_has_xml_sections(self):
        """기본 프롬프트에 XML 태그 섹션이 포함"""
        result = build_prompt(
            context="대화 기록",
            question="이 코드 분석해줘",
            file_context="",
            slack_context="<slack-context>\nchannel_id: C123\n</slack-context>",
        )
        assert "<slack-context>" in result
        assert "<user-request>" in result
        assert "</user-request>" in result

    def test_question_wrapped_in_user_request_tag(self):
        """사용자 질문이 <user-request> 태그로 감싸져야 함"""
        result = build_prompt(
            context="",
            question="안녕하세요",
            file_context="",
            slack_context="",
        )
        assert "<user-request>" in result
        assert "안녕하세요" in result
        assert "</user-request>" in result

    def test_file_context_wrapped_in_attachments_tag(self):
        """첨부 파일 컨텍스트가 <attachments> 태그로 감싸져야 함"""
        result = build_prompt(
            context="",
            question="파일 분석해줘",
            file_context="[파일: test.py, 타입: text, 크기: 100B]",
            slack_context="",
        )
        assert "<attachments>" in result
        assert "</attachments>" in result
        assert "test.py" in result

    def test_no_file_context_no_attachments_tag(self):
        """첨부 파일이 없으면 <attachments> 태그 생략"""
        result = build_prompt(
            context="",
            question="질문입니다",
            file_context="",
            slack_context="",
        )
        assert "<attachments>" not in result

    def test_channel_history_preserved(self):
        """채널 히스토리 컨텍스트가 포함"""
        result = build_prompt(
            context="<channel-history>\n[C123:1.0] <U1>: 안녕\n</channel-history>",
            question="요약해줘",
            file_context="",
            slack_context="",
        )
        assert "<channel-history>" in result
        assert "안녕" in result

    def test_section_ordering(self):
        """섹션 순서: slack-context -> channel-history -> user-request -> attachments"""
        result = build_prompt(
            context="<channel-history>\nhistory\n</channel-history>",
            question="질문",
            file_context="파일 정보",
            slack_context="<slack-context>\nmetadata\n</slack-context>",
        )
        ctx_idx = result.index("<slack-context>")
        hist_idx = result.index("<channel-history>")
        req_idx = result.index("<user-request>")
        attach_idx = result.index("<attachments>")
        assert ctx_idx < hist_idx < req_idx < attach_idx

    def test_empty_question_no_user_request_tag(self):
        """질문이 비어있으면 <user-request> 태그 생략"""
        result = build_prompt(
            context="기록",
            question="",
            file_context="파일 정보",
            slack_context="",
        )
        assert "<user-request>" not in result

    def test_no_trailing_instruction(self):
        """기존의 '위 컨텍스트를 참고하여' 안내문이 제거됨"""
        result = build_prompt(
            context="",
            question="질문",
            file_context="",
            slack_context="",
        )
        assert "위 컨텍스트를 참고하여" not in result
