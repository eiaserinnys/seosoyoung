"""slackbot management 서버 cogito 리플렉션 테스트.

create_management_app을 직접 호출하여 FastAPI TestClient로 테스트.
SocketModeHandler 기동 없이 management app만 단독으로 테스트한다.
"""

from fastapi.testclient import TestClient
from cogito import Reflector
from seosoyoung.slackbot.shutdown import create_management_app


class TestBotReflectEndpoints:
    """bot의 /reflect 엔드포인트 검증."""

    @staticmethod
    def _make_app():
        reflect = Reflector(
            name="bot",
            description="서소영 Slack SocketMode 봇",
            version_from="1.0.0",
            language="python",
            port=3106,
        )
        reflect.declare_capability(
            name="event_handling",
            description="Slack SocketMode를 통한 실시간 이벤트 수신 및 처리",
        )
        reflect.declare_capability(
            name="mention_response",
            description="@seosoyoung 멘션 감지 및 응답",
        )
        reflect.declare_capability(
            name="plugin_system",
            description="config/plugins.yaml 기반 동적 플러그인 로딩",
        )
        reflect.declare_capability(
            name="soulstream_integration",
            description="soulstream에 Claude Code 세션 위임 및 SSE 스트리밍",
        )
        return create_management_app(reflect, lambda: None)

    def test_level0_identity(self):
        client = TestClient(self._make_app())
        resp = client.get("/reflect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["identity"]["name"] == "bot"
        assert data["identity"]["port"] == 3106

    def test_capability_count(self):
        client = TestClient(self._make_app())
        resp = client.get("/reflect")
        data = resp.json()
        assert len(data["capabilities"]) == 4

    def test_capability_names(self):
        client = TestClient(self._make_app())
        resp = client.get("/reflect")
        data = resp.json()
        cap_names = {c["name"] for c in data["capabilities"]}
        assert cap_names == {
            "event_handling",
            "mention_response",
            "plugin_system",
            "soulstream_integration",
        }


class TestBotShutdownEndpoint:
    """bot의 /shutdown 엔드포인트 검증."""

    def test_shutdown_returns_200(self):
        import time

        called = []
        reflect = Reflector(
            name="bot", description="t", version_from="1.0.0", language="python", port=3106,
        )
        app = create_management_app(reflect, lambda: called.append(True))
        client = TestClient(app)

        resp = client.post("/shutdown")
        assert resp.status_code == 200
        assert resp.json()["status"] == "shutting down"
        time.sleep(0.3)
        assert called, "shutdown callback was not invoked"
