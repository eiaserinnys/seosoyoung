"""이미지 생성 모듈 테스트

마커 파싱 및 Gemini API 호출 테스트
"""

import re
import asyncio
import pytest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestImageGenMarkerParsing:
    """IMAGE_GEN 마커 파싱 테스트"""

    def test_single_marker(self):
        """단일 IMAGE_GEN 마커 추출"""
        output = "이미지를 생성합니다.\n<!-- IMAGE_GEN: 귀여운 강아지 -->"
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        assert prompts == ["귀여운 강아지"]

    def test_multiple_markers(self):
        """복수 IMAGE_GEN 마커 추출"""
        output = (
            "두 개의 이미지를 생성합니다.\n"
            "<!-- IMAGE_GEN: 해변의 석양 -->\n"
            "<!-- IMAGE_GEN: 우주 배경의 고양이 -->"
        )
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        assert prompts == ["해변의 석양", "우주 배경의 고양이"]

    def test_no_markers(self):
        """마커 없는 경우"""
        output = "일반 텍스트 응답입니다."
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        assert prompts == []

    def test_mixed_markers(self):
        """IMAGE_GEN과 다른 마커 혼합"""
        output = (
            "<!-- ATTACH: D:\\test\\file.md -->\n"
            "<!-- IMAGE_GEN: 판타지 성 -->\n"
            "<!-- FILE: /test/code.py -->\n"
            "<!-- UPDATE -->"
        )
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        attachments = re.findall(r"<!-- ATTACH: (.+?) -->", output)
        assert prompts == ["판타지 성"]
        assert attachments == ["D:\\test\\file.md"]

    def test_korean_prompt(self):
        """한글 프롬프트 파싱"""
        output = "<!-- IMAGE_GEN: 조선시대 양반가의 정원에 앉아있는 여인 -->"
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        assert prompts == ["조선시대 양반가의 정원에 앉아있는 여인"]

    def test_english_prompt(self):
        """영문 프롬프트 파싱"""
        output = "<!-- IMAGE_GEN: A cute puppy sitting on a bench in a park -->"
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        assert prompts == ["A cute puppy sitting on a bench in a park"]

    def test_prompt_with_special_chars(self):
        """특수문자 포함 프롬프트"""
        output = '<!-- IMAGE_GEN: fantasy castle, 4K, ultra-detailed (style: watercolor) -->'
        prompts = re.findall(r"<!-- IMAGE_GEN: (.+?) -->", output)
        assert prompts == ["fantasy castle, 4K, ultra-detailed (style: watercolor)"]


@dataclass
class MockSystemMessage:
    session_id: str = None


@dataclass
class MockTextBlock:
    text: str


@dataclass
class MockAssistantMessage:
    content: list


@dataclass
class MockResultMessage:
    result: str
    session_id: str = None


@pytest.mark.asyncio
class TestClaudeResultImageGenPrompts:
    """ClaudeResult에 image_gen_prompts가 올바르게 설정되는지 테스트"""

    async def test_image_gen_prompts_extracted(self):
        """IMAGE_GEN 마커가 ClaudeResult.image_gen_prompts로 추출되는지 확인"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockResultMessage(
                result="이미지를 생성합니다.\n<!-- IMAGE_GEN: 귀여운 강아지 -->",
                session_id="img-test"
            )

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.success is True
        assert result.image_gen_prompts == ["귀여운 강아지"]

    async def test_multiple_image_gen_prompts(self):
        """복수 IMAGE_GEN 마커 추출"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockResultMessage(
                result="<!-- IMAGE_GEN: 해변 -->\n<!-- IMAGE_GEN: 산 -->",
                session_id="img-test"
            )

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.image_gen_prompts == ["해변", "산"]

    async def test_no_image_gen_prompts(self):
        """IMAGE_GEN 마커 없는 경우 빈 리스트"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockResultMessage(
                result="일반 응답입니다.",
                session_id="img-test"
            )

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.image_gen_prompts == []

    async def test_image_gen_with_other_markers(self):
        """다른 마커와 혼합된 IMAGE_GEN"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner()

        async def mock_query(prompt, options):
            yield MockResultMessage(
                result=(
                    "결과\n"
                    "<!-- ATTACH: /path/file.md -->\n"
                    "<!-- IMAGE_GEN: 판타지 성 -->\n"
                    "<!-- UPDATE -->"
                ),
                session_id="img-test"
            )

        with patch("seosoyoung.claude.agent_runner.query", mock_query):
            with patch("seosoyoung.claude.agent_runner.ResultMessage", MockResultMessage):
                result = await runner.run("테스트")

        assert result.image_gen_prompts == ["판타지 성"]
        assert result.attachments == ["/path/file.md"]
        assert result.update_requested is True


@pytest.mark.asyncio
class TestGeminiImageGenerator:
    """Gemini API 이미지 생성 모킹 테스트"""

    async def test_generate_image_success(self, tmp_path):
        """이미지 생성 성공"""
        from seosoyoung.image_gen.generator import generate_image, IMAGE_GEN_DIR

        # Mock Gemini 응답
        mock_blob = MagicMock()
        mock_blob.mime_type = "image/png"
        mock_blob.data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # 가짜 PNG 데이터

        mock_part = MagicMock()
        mock_part.inline_data = mock_blob
        mock_part.text = None

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response

        mock_client = MagicMock()
        mock_client.models = mock_models

        with patch("seosoyoung.image_gen.generator.genai.Client", return_value=mock_client):
            with patch("seosoyoung.image_gen.generator.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.image_gen.generator.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("귀여운 강아지")

        assert result.path.exists()
        assert result.mime_type == "image/png"
        assert result.prompt == "귀여운 강아지"
        assert result.path.suffix == ".png"

    async def test_generate_image_no_api_key(self):
        """API 키 없는 경우"""
        from seosoyoung.image_gen.generator import generate_image

        with patch("seosoyoung.image_gen.generator.Config.GEMINI_API_KEY", None):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                await generate_image("test")

    async def test_generate_image_empty_response(self):
        """빈 응답 처리"""
        from seosoyoung.image_gen.generator import generate_image

        mock_response = MagicMock()
        mock_response.candidates = []

        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response

        mock_client = MagicMock()
        mock_client.models = mock_models

        with patch("seosoyoung.image_gen.generator.genai.Client", return_value=mock_client):
            with patch("seosoyoung.image_gen.generator.Config.GEMINI_API_KEY", "test-key"):
                with pytest.raises(RuntimeError, match="빈 응답"):
                    await generate_image("test")

    async def test_generate_image_text_only_response(self):
        """텍스트만 반환된 경우 (안전 필터 등)"""
        from seosoyoung.image_gen.generator import generate_image

        mock_part = MagicMock()
        mock_part.inline_data = None
        mock_part.text = "이 요청은 안전 정책에 의해 차단되었습니다."

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response

        mock_client = MagicMock()
        mock_client.models = mock_models

        with patch("seosoyoung.image_gen.generator.genai.Client", return_value=mock_client):
            with patch("seosoyoung.image_gen.generator.Config.GEMINI_API_KEY", "test-key"):
                with pytest.raises(RuntimeError, match="이미지를 생성하지 못했습니다"):
                    await generate_image("test")

    async def test_generate_image_jpg_format(self, tmp_path):
        """JPEG 형식 이미지 저장"""
        from seosoyoung.image_gen.generator import generate_image

        mock_blob = MagicMock()
        mock_blob.mime_type = "image/jpeg"
        mock_blob.data = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # 가짜 JPEG 데이터

        mock_part = MagicMock()
        mock_part.inline_data = mock_blob
        mock_part.text = None

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response

        mock_client = MagicMock()
        mock_client.models = mock_models

        with patch("seosoyoung.image_gen.generator.genai.Client", return_value=mock_client):
            with patch("seosoyoung.image_gen.generator.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.image_gen.generator.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("sunset")

        assert result.path.suffix == ".jpg"
        assert result.mime_type == "image/jpeg"

    async def test_generate_image_custom_model(self, tmp_path):
        """커스텀 모델 지정"""
        from seosoyoung.image_gen.generator import generate_image

        mock_blob = MagicMock()
        mock_blob.mime_type = "image/png"
        mock_blob.data = b"\x89PNG" + b"\x00" * 100

        mock_part = MagicMock()
        mock_part.inline_data = mock_blob
        mock_part.text = None

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        mock_models = MagicMock()
        mock_models.generate_content.return_value = mock_response

        mock_client = MagicMock()
        mock_client.models = mock_models

        with patch("seosoyoung.image_gen.generator.genai.Client", return_value=mock_client):
            with patch("seosoyoung.image_gen.generator.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.image_gen.generator.IMAGE_GEN_DIR", tmp_path):
                    await generate_image("test", model="gemini-2.5-flash-image")

        # generate_content가 지정된 모델로 호출되었는지 확인
        call_kwargs = mock_models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-2.5-flash-image"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
