"""이미지 생성 모듈 테스트

OpenAI gpt-image-2 API 호출 및 MCP 도구 테스트
"""

import asyncio
import base64
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import seosoyoung.mcp.tools.image_gen as _image_gen_mod

# _OPENAI_API_KEY 패치 경로
_API_KEY_PATH = "seosoyoung.mcp.tools.image_gen._OPENAI_API_KEY"

# 테스트용 PNG 바이트
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_FAKE_PNG_B64 = base64.b64encode(_FAKE_PNG).decode()


def _make_openai_response(b64_json=None):
    """OpenAI images API 응답 mock 생성"""
    mock_image = MagicMock()
    mock_image.b64_json = b64_json if b64_json is not None else _FAKE_PNG_B64

    mock_response = MagicMock()
    mock_response.data = [mock_image]
    return mock_response


def _make_empty_response():
    """빈 data 응답"""
    mock_response = MagicMock()
    mock_response.data = []
    return mock_response


def _make_no_b64_response():
    """b64_json이 None인 응답"""
    mock_image = MagicMock()
    mock_image.b64_json = None

    mock_response = MagicMock()
    mock_response.data = [mock_image]
    return mock_response


@pytest.mark.asyncio
class TestOpenAIImageGenerator:
    """OpenAI gpt-image-2 이미지 생성 모킹 테스트"""

    def _make_mock_client(self, generate_response=None, edit_response=None):
        """AsyncOpenAI 클라이언트 mock"""
        mock_client = MagicMock()
        mock_images = MagicMock()

        if generate_response is not None:
            mock_images.generate = AsyncMock(return_value=generate_response)
        else:
            mock_images.generate = AsyncMock(return_value=_make_openai_response())

        if edit_response is not None:
            mock_images.edit = AsyncMock(return_value=edit_response)
        else:
            mock_images.edit = AsyncMock(return_value=_make_openai_response())

        mock_client.images = mock_images
        return mock_client

    async def test_generate_image_success(self, tmp_path):
        """이미지 생성 성공"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("귀여운 강아지")

        assert result.path.exists()
        assert result.mime_type == "image/png"
        assert result.prompt == "귀여운 강아지"
        assert result.path.suffix == ".png"
        # images.generate가 호출되었는지 확인
        client.images.generate.assert_called_once()

    async def test_generate_image_no_api_key(self):
        """API 키 없는 경우"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        with patch(_API_KEY_PATH, ""):
            with pytest.raises(ValueError, match="OPENAI_API_KEY"):
                await generate_image("test")

    async def test_generate_image_empty_response(self):
        """빈 응답 처리"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client(generate_response=_make_empty_response())

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with pytest.raises(RuntimeError, match="빈 응답"):
                    await generate_image("test")

    async def test_generate_image_no_b64_data(self):
        """b64_json이 None인 응답"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client(generate_response=_make_no_b64_response())

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with pytest.raises(RuntimeError, match="이미지 데이터를 찾을 수 없습니다"):
                    await generate_image("test")

    async def test_generate_image_always_png(self, tmp_path):
        """gpt-image-2는 항상 PNG를 반환"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("sunset")

        assert result.path.suffix == ".png"
        assert result.mime_type == "image/png"

    async def test_generate_image_with_reference_images(self, tmp_path):
        """레퍼런스 이미지 포함 생성 — images.edit() 호출"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        ref_img = tmp_path / "reference.png"
        ref_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "similar style dog",
                        reference_images=[str(ref_img)],
                    )

        assert result.path.exists()
        # images.edit()가 호출되었는지 확인
        client.images.edit.assert_called_once()
        client.images.generate.assert_not_called()
        # 프롬프트 확인
        call_kwargs = client.images.edit.call_args
        assert call_kwargs.kwargs["prompt"] == "similar style dog"

    async def test_generate_image_with_multiple_reference_images(self, tmp_path):
        """복수 레퍼런스 이미지 포함 생성"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        ref1 = tmp_path / "ref1.png"
        ref1.write_bytes(b"\x89PNG" + b"\x00" * 50)
        ref2 = tmp_path / "ref2.jpg"
        ref2.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "blend these",
                        reference_images=[str(ref1), str(ref2)],
                    )

        client.images.edit.assert_called_once()
        # image 파라미터에 파일 핸들 리스트가 전달되었는지 확인
        call_kwargs = client.images.edit.call_args
        image_arg = call_kwargs.kwargs["image"]
        assert len(image_arg) == 2

    async def test_generate_image_edit_with_quality(self, tmp_path):
        """레퍼런스 이미지 + quality 파라미터 전달 — images.edit()에도 quality 적용"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        ref_img = tmp_path / "reference.png"
        ref_img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "high quality ref",
                        reference_images=[str(ref_img)],
                        quality="high",
                    )

        client.images.edit.assert_called_once()
        call_kwargs = client.images.edit.call_args
        assert call_kwargs.kwargs["quality"] == "high"

    async def test_generate_image_reference_nonexistent_fallback(self, tmp_path):
        """존재하지 않는 레퍼런스 이미지는 무시, 전부 무효 시 generate() 폴백"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "test",
                        reference_images=[str(tmp_path / "nonexistent.png")],
                    )

        # 유효한 레퍼런스 없으면 generate()로 폴백
        client.images.generate.assert_called_once()
        client.images.edit.assert_not_called()

    async def test_generate_image_without_reference_images(self, tmp_path):
        """레퍼런스 이미지 없이 호출"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("simple prompt")

        client.images.generate.assert_called_once()
        call_kwargs = client.images.generate.call_args
        assert call_kwargs.kwargs["prompt"] == "simple prompt"

    async def test_generate_image_with_size(self, tmp_path):
        """size 파라미터 전달"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("wide banner", size="1536x1024")

        assert result.path.exists()
        call_kwargs = client.images.generate.call_args
        assert call_kwargs.kwargs["size"] == "1536x1024"

    async def test_generate_image_with_quality(self, tmp_path):
        """quality 파라미터 전달"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image("high quality art", quality="high")

        call_kwargs = client.images.generate.call_args
        assert call_kwargs.kwargs["quality"] == "high"

    async def test_generate_image_with_size_and_quality(self, tmp_path):
        """size + quality 동시 전달"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    result = await generate_image(
                        "cinematic shot", size="1024x1536", quality="high"
                    )

        call_kwargs = client.images.generate.call_args
        assert call_kwargs.kwargs["size"] == "1024x1536"
        assert call_kwargs.kwargs["quality"] == "high"

    async def test_generate_image_defaults_when_no_params(self, tmp_path):
        """size, quality 미지정 시 기본값 'auto' 전달"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        client = self._make_mock_client()

        with patch("seosoyoung.mcp.tools.image_gen.AsyncOpenAI", return_value=client):
            with patch(_API_KEY_PATH, "test-key"):
                with patch("seosoyoung.mcp.tools.image_gen.IMAGE_GEN_DIR", tmp_path):
                    await generate_image("default settings")

        call_kwargs = client.images.generate.call_args
        assert call_kwargs.kwargs["size"] == "auto"
        assert call_kwargs.kwargs["quality"] == "auto"

    async def test_generate_image_invalid_size(self):
        """잘못된 size 검증"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        with patch(_API_KEY_PATH, "test-key"):
            with pytest.raises(ValueError, match="지원하지 않는 이미지 크기"):
                await generate_image("test", size="8K")

    async def test_generate_image_invalid_quality(self):
        """잘못된 quality 검증"""
        from seosoyoung.mcp.tools.image_gen import generate_image

        with patch(_API_KEY_PATH, "test-key"):
            with pytest.raises(ValueError, match="지원하지 않는 품질"):
                await generate_image("test", quality="ultra")


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

        with patch("seosoyoung.mcp.tools.image_gen.generate_image", new_callable=AsyncMock, side_effect=ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")):
            result = await generate_and_upload_image(
                "test", "C123", "T123"
            )

        assert result["success"] is False
        assert "OPENAI_API_KEY" in result["message"]

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
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs["reference_images"] == ["/path/to/ref1.png", "/path/to/ref2.jpg"]

    async def test_with_size_and_quality(self, tmp_path):
        """size, quality 파라미터 전달"""
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
                    "high res art", "C123", "T123",
                    size="1536x1024",
                    quality="high",
                )

        assert result["success"] is True
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs["size"] == "1536x1024"
        assert call_kwargs.kwargs["quality"] == "high"

    async def test_empty_size_and_quality_passed_as_none(self, tmp_path):
        """빈 문자열은 None으로 변환되어 전달"""
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
                    "default", "C123", "T123",
                    size="",
                    quality="",
                )

        assert result["success"] is True
        call_kwargs = mock_gen.call_args
        assert call_kwargs.kwargs["size"] is None
        assert call_kwargs.kwargs["quality"] is None

    async def test_invalid_size_returns_error(self):
        """잘못된 size가 전달되면 에러 반환"""
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        with patch(_API_KEY_PATH, "test-key"):
            result = await generate_and_upload_image(
                "test", "C123", "T123", size="8K"
            )

        assert result["success"] is False
        assert "지원하지 않는 이미지 크기" in result["message"]

    async def test_invalid_quality_returns_error(self):
        """잘못된 quality가 전달되면 에러 반환"""
        from seosoyoung.mcp.tools.image_gen import generate_and_upload_image

        with patch(_API_KEY_PATH, "test-key"):
            result = await generate_and_upload_image(
                "test", "C123", "T123", quality="ultra"
            )

        assert result["success"] is False
        assert "지원하지 않는 품질" in result["message"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
