"""mcp-seosoyoung cogito 리플렉션 통합 테스트.

FastMCP의 custom_route로 등록된 /reflect 엔드포인트와
Reflector 메타데이터를 검증한다.
"""

import pytest
import httpx

from seosoyoung.mcp.server import mcp, reflect


# --- Reflector 메타데이터 테스트 ---


class TestReflectorIdentity:
    def test_name(self):
        assert reflect.identity.name == "mcp-seosoyoung"

    def test_description(self):
        assert reflect.identity.description == "서소영 봇 전용 MCP 서버"

    def test_port(self):
        assert reflect.identity.port == 3104

    def test_transport(self):
        assert reflect.identity.transport == "sse"


class TestCapabilities:
    """5개 capability가 올바르게 등록되었는지 검증."""

    def test_capability_count(self):
        caps = reflect.get_capabilities()
        assert len(caps) == 5

    def test_capability_names(self):
        cap_names = {c.name for c in reflect.get_capabilities()}
        expected = {
            "file_attachment",
            "messaging",
            "image_generation",
            "thread_files",
            "user_profile",
        }
        assert cap_names == expected

    def test_file_attachment_tools(self):
        caps = {c.name: c for c in reflect.get_capabilities()}
        assert caps["file_attachment"].tools == ["slack_attach_file"]

    def test_messaging_tools(self):
        caps = {c.name: c for c in reflect.get_capabilities()}
        assert caps["messaging"].tools == ["slack_post_message"]

    def test_image_generation_tools(self):
        caps = {c.name: c for c in reflect.get_capabilities()}
        assert caps["image_generation"].tools == ["slack_generate_image"]

    def test_thread_files_tools(self):
        caps = {c.name: c for c in reflect.get_capabilities()}
        assert caps["thread_files"].tools == ["slack_download_thread_files"]

    def test_user_profile_tools(self):
        """user_profile capability에 2개 도구가 등록되어 있는지 확인."""
        caps = {c.name: c for c in reflect.get_capabilities()}
        assert set(caps["user_profile"].tools) == {
            "slack_get_user_profile",
            "slack_download_user_avatar",
        }


class TestConfigs:
    """각 capability에 올바른 config가 연결되어 있는지 검증."""

    def test_file_attachment_config(self):
        configs = reflect.get_configs("file_attachment")
        assert len(configs) == 1
        assert configs[0].key == "SLACK_BOT_TOKEN"
        assert configs[0].sensitive is True

    def test_messaging_config(self):
        configs = reflect.get_configs("messaging")
        assert len(configs) == 1
        assert configs[0].key == "SLACK_BOT_TOKEN"

    def test_image_generation_config(self):
        configs = reflect.get_configs("image_generation")
        assert len(configs) == 1
        assert configs[0].key == "GEMINI_API_KEY"
        assert configs[0].sensitive is True

    def test_thread_files_config(self):
        configs = reflect.get_configs("thread_files")
        assert len(configs) == 1
        assert configs[0].key == "SLACK_BOT_TOKEN"

    def test_user_profile_config(self):
        configs = reflect.get_configs("user_profile")
        assert len(configs) == 1
        assert configs[0].key == "SLACK_BOT_TOKEN"


# --- HTTP 엔드포인트 테스트 ---
# FastMCP의 http_app(transport="sse")으로 Starlette 앱을 생성하고
# httpx ASGI transport로 직접 테스트한다.


@pytest.fixture(scope="module")
def sse_app():
    """FastMCP SSE 앱 (custom_route 포함)."""
    return mcp.http_app(transport="sse")


class TestReflectEndpoints:
    """ASGI transport는 AsyncClient가 필요하므로 async 테스트로 작성."""

    @pytest.mark.asyncio
    async def test_level0(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "capabilities" in data
        assert data["identity"]["name"] == "mcp-seosoyoung"
        assert len(data["capabilities"]) == 5

    @pytest.mark.asyncio
    async def test_config_all(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "configs" in data
        assert len(data["configs"]) >= 5  # 5 capabilities, each with at least 1 config

    @pytest.mark.asyncio
    async def test_config_by_capability(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect/config/image_generation")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["configs"]) == 1
        assert data["configs"][0]["key"] == "GEMINI_API_KEY"

    @pytest.mark.asyncio
    async def test_source_all(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect/source")
        assert resp.status_code == 200
        data = resp.json()
        assert "sources" in data
        # 5 capabilities with functions → 5 source entries
        assert len(data["sources"]) == 5

    @pytest.mark.asyncio
    async def test_source_by_capability(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect/source/file_attachment")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sources"]) == 1

    @pytest.mark.asyncio
    async def test_runtime(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect/runtime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "pid" in data
        assert "uptime_seconds" in data

    @pytest.mark.asyncio
    async def test_full(self, sse_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=sse_app), base_url="http://test"
        ) as client:
            resp = await client.get("/reflect/full")
        assert resp.status_code == 200
        data = resp.json()
        assert "identity" in data
        assert "capabilities" in data
        assert "configs" in data
        assert "sources" in data
        assert "runtime" in data


class TestMcpToolsStillRegistered:
    """cogito 데코레이터 추가 후에도 MCP 도구 등록이 유지되는지 확인."""

    @pytest.mark.asyncio
    async def test_tool_count(self):
        tools = await mcp.get_tools()
        assert len(tools) == 6

    @pytest.mark.asyncio
    async def test_tool_names(self):
        tools = await mcp.get_tools()
        tool_names = set(tools.keys())
        expected = {
            "slack_attach_file",
            "slack_post_message",
            "slack_generate_image",
            "slack_download_thread_files",
            "slack_get_user_profile",
            "slack_download_user_avatar",
        }
        assert tool_names == expected
