"""이미지 생성 모듈 테스트

Gemini API 호출 및 MCP 도구 테스트
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.mark.asyncio
class TestGeminiImageGenerator:
    """Gemini API 이미지 생성 모킹 테스트"""

    def _make_mock_response(self, mime_type="image/png", data=None):
        """Gemini 응답 모킹 헬퍼"""
        mock_blob = MagicMock()
        mock_blob.mime_type = mime_type
        mock_blob.data = data or b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_part = MagicMock()
        mock_part.inline_data = mock_blob
        mock_part.text = None

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        return mock_response

    def _make_mock_client(self, response):
        """Gemini 클라이언트 모킹 헬퍼"""
        mock_models = MagicMock()
        mock_models.generate_content.return_value = response
        mock_client = MagicMock()
        mock_client.models = mock_models
        return mock_client

    async def test_generate_image_success(self, tmp_path):
        """이미지 생성 성공"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        response = self._make_mock_response()
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("귀여운 강아지")

        assert result.path.exists()
        assert result.mime_type == "image/png"
        assert result.prompt == "귀여운 강아지"
        assert result.path.suffix == ".png"

    async def test_generate_image_no_api_key(self):
        """API 키 없는 경우"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", None):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                await generate_image("test")

    async def test_generate_image_empty_response(self):
        """빈 응답 처리"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        mock_response = MagicMock()
        mock_response.candidates = []

        client = self._make_mock_client(mock_response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with pytest.raises(RuntimeError, match="빈 응답"):
                    await generate_image("test")

    async def test_generate_image_text_only_response(self):
        """텍스트만 반환된 경우 (안전 필터 등)"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        mock_part = MagicMock()
        mock_part.inline_data = None
        mock_part.text = "이 요청은 안전 정책에 의해 차단되었습니다."

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]

        client = self._make_mock_client(mock_response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with pytest.raises(RuntimeError, match="이미지를 생성하지 못했습니다"):
                    await generate_image("test")

    async def test_generate_image_jpg_format(self, tmp_path):
        """JPEG 형식 이미지 저장"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        response = self._make_mock_response(
            mime_type="image/jpeg",
            data=b"\xff\xd8\xff\xe0" + b"\x00" * 100,
        )
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("sunset")

        assert result.path.suffix == ".jpg"
        assert result.mime_type == "image/jpeg"

    async def test_generate_image_custom_model(self, tmp_path):
        """커스텀 모델 지정"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        response = self._make_mock_response()
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    await generate_image("test", model="gemini-2.5-flash-image")

        call_kwargs = client.models.generate_content.call_args
        assert call_kwargs.kwargs["model"] == "gemini-2.5-flash-image"

    async def test_generate_image_with_reference_images(self, tmp_path):
        """레퍼런스 이미지 포함 생성"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        # 레퍼런스 이미지 파일 생성
        ref_img = tmp_path / "reference.png"
        ref_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        response = self._make_mock_response()
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "similar style dog",
                        reference_images=[str(ref_img)],
                    )

        assert result.path.exists()
        # contents가 리스트로 전달되었는지 확인 (ref_part + prompt 텍스트)
        call_kwargs = client.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        assert isinstance(contents, list)
        assert len(contents) == 2  # 1 ref_part + 1 prompt string
        assert contents[-1] == "similar style dog"

    async def test_generate_image_with_multiple_reference_images(self, tmp_path):
        """복수 레퍼런스 이미지 포함 생성"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        ref1 = tmp_path / "ref1.png"
        ref1.write_bytes(b"\x89PNG" + b"\x00" * 50)
        ref2 = tmp_path / "ref2.jpg"
        ref2.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

        response = self._make_mock_response()
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "blend these",
                        reference_images=[str(ref1), str(ref2)],
                    )

        call_kwargs = client.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        assert isinstance(contents, list)
        assert len(contents) == 3  # 2 refs + 1 prompt

    async def test_generate_image_reference_nonexistent_skipped(self, tmp_path):
        """존재하지 않는 레퍼런스 이미지는 무시"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        response = self._make_mock_response()
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "test",
                        reference_images=[str(tmp_path / "nonexistent.png")],
                    )

        # 레퍼런스가 모두 스킵되면 contents는 문자열(프롬프트만)
        call_kwargs = client.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        assert contents == "test"

    async def test_generate_image_without_reference_images(self, tmp_path):
        """레퍼런스 이미지 없이 호출 (기존 동작 호환)"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        response = self._make_mock_response()
        client = self._make_mock_client(response)

        with patch("seosoyoung.mcp.tools.image_gen.genai.Client", return_value=client):
            with patch("seosoyoung.mcp.tools.image_gen.Config.GEMINI_API_KEY", "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("simple prompt")

        call_kwargs = client.models.generate_content.call_args
        contents = call_kwargs.kwargs["contents"]
        assert contents == "simple prompt"


@pytest.mark.asyncio
class TestMcpGenerateAndUploadImage:
    """MCP 도구 generate_and_upload_image 테스트"""

    async def test_success(self, tmp_path):
        """정상 생성 및 업로드"""
        from seosoyoung.mcp.tools.image_gen import GeneratedImage
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        img_path = tmp_path / "generated.png"
        img_path.write_bytes(b"\x89PNG" + b"\x00" * 100)

        mock_generated = GeneratedImage(
            path=img_path, mime_type="image/png", prompt="cute dog"
        )

        mock_client = MagicMock()

        with patch("seosoyoung.mcp.tools.image_gen.generate_image", new_callable=AsyncMock, return_value=mock_generated):
            with patch("seosoyoung.mcp.tools.image_gen.WebClient", return_value=mock_client):
                result = await generate_and_upload_image(
                    "cute dog", "C123", "T123"
                )

        assert result["success"] is True
        assert "file_name" in result
        mock_client.files_upload_v2.assert_called_once()

    async def test_api_key_missing(self):
        """API 키 미설정"""
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        with patch("seosoyoung.mcp.tools.image_gen.generate_image", new_callable=AsyncMock, side_effect=ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")):
            result = await generate_and_upload_image(
                "test", "C123", "T123"
            )

        assert result["success"] is False
        assert "GEMINI_API_KEY" in result["message"]

    async def test_generation_failure(self):
        """이미지 생성 실패"""
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        with patch("seosoyoung.mcp.tools.image_gen.generate_image", new_callable=AsyncMock, side_effect=RuntimeError("빈 응답")):
            result = await generate_and_upload_image(
                "test", "C123", "T123"
            )

        assert result["success"] is False
        assert "빈 응답" in result["message"]

    async def test_upload_failure(self, tmp_path):
        """업로드 실패"""
        from seosoyoung.mcp.tools.image_gen import GeneratedImage
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        img_path = tmp_path / "generated.png"
        img_path.write_bytes(b"\x89PNG" + b"\x00" * 100)

        mock_generated = GeneratedImage(
            path=img_path, mime_type="image/png", prompt="test"
        )

        mock_client = MagicMock()
        mock_client.files_upload_v2.side_effect = Exception("Slack API error")

        with patch("seosoyoung.mcp.tools.image_gen.generate_image", new_callable=AsyncMock, return_value=mock_generated):
            with patch("seosoyoung.mcp.tools.image_gen.WebClient", return_value=mock_client):
                result = await generate_and_upload_image(
                    "test", "C123", "T123"
                )

        assert result["success"] is False
        assert "업로드 실패" in result["message"]

    async def test_with_reference_image_paths(self, tmp_path):
        """레퍼런스 이미지 경로 전달"""
        from seosoyoung.mcp.tools.image_gen import GeneratedImage
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        img_path = tmp_path / "generated.png"
        img_path.write_bytes(b"\x89PNG" + b"\x00" * 100)

        mock_generated = GeneratedImage(
            path=img_path, mime_type="image/png", prompt="test"
        )

        mock_gen = AsyncMock(return_value=mock_generated)
        mock_client = MagicMock()

        with patch("seosoyoung.mcp.tools.image_gen.generate_image", mock_gen):
            with patch("seosoyoung.mcp.tools.image_gen.WebClient", return_value=mock_client):
                result = await generate_and_upload_image(
                    "blend style", "C123", "T123",
                    reference_image_paths="/path/to/ref1.png, /path/to/ref2.jpg"
                )

        assert result["success"] is True
        # generate_image에 reference_images 리스트 전달 확인
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs["reference_images"] == ["/path/to/ref1.png", "/path/to/ref2.jpg"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
