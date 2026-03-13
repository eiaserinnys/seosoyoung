"""rescue-bot management 서버 cogito 리플렉션 테스트.

create_management_app을 직접 호출하여 FastAPI TestClient로 테스트.
SocketModeHandler 기동 없이 management app만 단독으로 테스트한다.
"""

from fastapi.testclient import TestClient
from cogito import Reflector
from seosoyoung.rescue.shutdown import create_management_app


class TestRescueBotReflectEndpoints:
    """rescue-bot의 /reflect 엔드포인트 검증."""

    @staticmethod
    def _make_app():
        reflect = Reflector(
            name="rescue-bot",
            description="서소영 긴급 복구용 봇",
            version_from="1.0.0",
            language="python",
            port=3107,
        )
        reflect.declare_capability(
            name="emergency_execution",
            description="Claude Code SDK를 직접 호출하여 soulstream 장애 시에도 명령을 처리",
        )
        reflect.declare_capability(
            name="standalone_operation",
            description="메인 봇과 독립된 Slack App으로 동작",
        )
        return create_management_app(reflect, lambda: None)

    def test_level0_identity(self):
        client = TestClient(self._make_app())
        resp = client.get("/reflect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["identity"]["name"] == "rescue-bot"
        assert data["identity"]["port"] == 3107

    def test_capability_count(self):
        client = TestClient(self._make_app())
        resp = client.get("/reflect")
        data = resp.json()
        assert len(data["capabilities"]) == 2

    def test_capability_names(self):
        client = TestClient(self._make_app())
        resp = client.get("/reflect")
        data = resp.json()
        cap_names = {c["name"] for c in data["capabilities"]}
        assert cap_names == {"emergency_execution", "standalone_operation"}


class TestRescueBotShutdownEndpoint:
    """rescue-bot의 /shutdown 엔드포인트 검증."""

    def test_shutdown_returns_200(self):
        import time

        called = []
        reflect = Reflector(
            name="rescue-bot", description="t", version_from="1.0.0", language="python", port=3107,
        )
        app = create_management_app(reflect, lambda: called.append(True))
        client = TestClient(app)

        resp = client.post("/shutdown")
        assert resp.status_code == 200
        assert resp.json()["status"] == "shutting down"
        time.sleep(0.3)
        assert called, "shutdown callback was not invoked"
