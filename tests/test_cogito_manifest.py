"""cogito composition manifest 테스트.

manifest 로드 및 compose 검증.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

from cogito.manifest import compose, load_manifest


class TestManifestLoad:
    """manifest 파일이 올바른 구조인지 검증."""

    @pytest.fixture
    def manifest_path(self):
        """워크스페이스 루트의 cogito-manifest.yaml 경로."""
        # 테스트 환경에서의 상대 경로 계산
        # tests/ → seosoyoung--cogito/ → .projects/ → slackbot_workspace/
        candidates = [
            Path(__file__).parent.parent.parent.parent / "cogito-manifest.yaml",
            Path("cogito-manifest.yaml"),
        ]
        for p in candidates:
            if p.exists():
                return p
        pytest.skip("cogito-manifest.yaml not found")

    def test_manifest_loads(self, manifest_path):
        data = load_manifest(manifest_path)
        assert "services" in data

    def test_service_count(self, manifest_path):
        data = load_manifest(manifest_path)
        assert len(data["services"]) == 3

    def test_internal_services(self, manifest_path):
        data = load_manifest(manifest_path)
        internal = [s for s in data["services"] if s.get("type") == "internal"]
        names = {s["name"] for s in internal}
        assert "mcp-seosoyoung" in names
        assert "soulstream-server" in names
        assert "bot" in names

    def test_external_services(self, manifest_path):
        data = load_manifest(manifest_path)
        external = [s for s in data["services"] if s.get("type") == "external"]
        # 현재 manifest에는 external 서비스가 없음 (internal 3개만 운영)
        assert len(external) == 0

    def test_external_have_static(self, manifest_path):
        data = load_manifest(manifest_path)
        external = [s for s in data["services"] if s.get("type") == "external"]
        for svc in external:
            assert "static" in svc, f"{svc['name']} missing static data"
            assert "identity" in svc["static"]

    def test_internal_have_endpoints(self, manifest_path):
        data = load_manifest(manifest_path)
        internal = [s for s in data["services"] if s.get("type") == "internal"]
        for svc in internal:
            assert "endpoint" in svc, f"{svc['name']} missing endpoint"
            assert svc["endpoint"].startswith("http://")


class TestManifestCompose:
    """compose 함수의 internal fetch + external static 병합 검증."""

    @pytest.fixture
    def mock_manifest(self, tmp_path):
        """테스트용 간단한 manifest."""
        data = {
            "services": [
                {
                    "name": "test-internal",
                    "endpoint": "http://localhost:9999/reflect",
                    "type": "internal",
                },
                {
                    "name": "test-external",
                    "type": "external",
                    "static": {
                        "identity": {
                            "name": "test-external",
                            "description": "외부 서비스",
                        },
                        "capabilities": [
                            {"name": "cap1", "description": "테스트 기능"}
                        ],
                    },
                },
            ]
        }
        path = tmp_path / "test-manifest.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        return path

    @pytest.mark.asyncio
    async def test_compose_external_returns_static(self, mock_manifest):
        """external 서비스는 manifest의 static 데이터를 그대로 반환."""
        with patch("cogito.manifest.fetch_service", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "identity": {"name": "test-internal"},
                "capabilities": [],
            }
            results = await compose(mock_manifest)

        assert len(results) == 2
        # external은 static 그대로
        external = results[1]
        assert external["identity"]["name"] == "test-external"
        assert len(external["capabilities"]) == 1

    @pytest.mark.asyncio
    async def test_compose_internal_fetches(self, mock_manifest):
        """internal 서비스는 fetch_service를 호출."""
        with patch("cogito.manifest.fetch_service", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "identity": {"name": "test-internal", "version": "abc123"},
                "capabilities": [{"name": "test_cap"}],
            }
            results = await compose(mock_manifest)

        mock_fetch.assert_called_once_with("http://localhost:9999/reflect")
        internal = results[0]
        assert internal["identity"]["name"] == "test-internal"

    @pytest.mark.asyncio
    async def test_compose_handles_unreachable(self, mock_manifest):
        """internal 서비스가 응답하지 않으면 error stub을 반환."""
        with patch("cogito.manifest.fetch_service", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {
                "identity": {"name": "http://localhost:9999/reflect", "status": "unreachable"},
                "error": "Connection refused",
            }
            results = await compose(mock_manifest)

        internal = results[0]
        assert "error" in internal
