"""
test_credentials_api - Credentials REST API 통합 테스트

FastAPI TestClient를 사용한 엔드포인트 통합 테스트.
인증(verify_token)은 테스트 환경에서 자동 우회됩니다
(CLAUDE_SERVICE_TOKEN 미설정 + development 모드).
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from seosoyoung.soul.service.credential_store import CredentialStore
from seosoyoung.soul.service.credential_swapper import CredentialSwapper
from seosoyoung.soul.api.credentials import create_credentials_router


CRED_TEAM = {
    "claudeAiOauth": {
        "accessToken": "fake-team-access-token-for-testing",
        "refreshToken": "fake-team-refresh-token-for-testing",
        "expiresAt": 1770300031040,
        "scopes": ["user:inference"],
        "subscriptionType": "team",
        "rateLimitTier": "default_raven",
    }
}

CRED_MAX = {
    "claudeAiOauth": {
        "accessToken": "fake-max-access-token-for-testing",
        "refreshToken": "fake-max-refresh-token-for-testing",
        "expiresAt": 1772208817068,
        "scopes": ["user:inference"],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_20x",
    }
}


@pytest.fixture
def setup(tmp_path: Path):
    """테스트용 앱, 클라이언트, store, swapper를 셋업."""
    profiles_dir = tmp_path / "profiles"
    cred_dir = tmp_path / ".claude"
    cred_dir.mkdir()
    cred_file = cred_dir / ".credentials.json"
    cred_file.write_text(json.dumps(CRED_TEAM), encoding="utf-8")

    store = CredentialStore(profiles_dir=profiles_dir)
    swapper = CredentialSwapper(store=store, credentials_path=cred_file)

    app = FastAPI()
    router = create_credentials_router(store=store, swapper=swapper)
    app.include_router(router, prefix="/profiles")

    client = TestClient(app)
    return {
        "client": client,
        "store": store,
        "swapper": swapper,
        "cred_file": cred_file,
        "profiles_dir": profiles_dir,
    }


class TestListProfiles:
    def test_list_empty(self, setup):
        resp = setup["client"].get("/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profiles"] == []
        assert data["active"] is None

    def test_list_with_profiles(self, setup):
        store = setup["store"]
        store.save("team", CRED_TEAM)
        store.save("personal", CRED_MAX)
        store.set_active("team")

        resp = setup["client"].get("/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["profiles"]) == 2
        assert data["active"] == "team"

        names = {p["name"] for p in data["profiles"]}
        assert names == {"team", "personal"}


class TestGetActive:
    def test_no_active(self, setup):
        resp = setup["client"].get("/profiles/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is None
        assert data["profile"] is None

    def test_with_active(self, setup):
        store = setup["store"]
        store.save("team", CRED_TEAM)
        store.set_active("team")

        resp = setup["client"].get("/profiles/active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] == "team"
        assert data["profile"]["subscriptionType"] == "team"


class TestSaveProfile:
    def test_save_current(self, setup):
        resp = setup["client"].post("/profiles/my_team")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my_team"
        assert data["saved"] is True

        # store에 저장됐는지 확인
        profile = setup["store"].get("my_team")
        assert profile is not None
        assert profile["claudeAiOauth"]["subscriptionType"] == "team"

    def test_save_invalid_name(self, setup):
        # '../' 는 FastAPI 라우터가 정규화하므로, 선두 언더스코어로 테스트
        resp = setup["client"].post("/profiles/_hidden")
        assert resp.status_code == 400

    def test_save_reserved_name(self, setup):
        resp = setup["client"].post("/profiles/_active")
        assert resp.status_code == 400


class TestActivateProfile:
    def test_activate_existing(self, setup):
        store = setup["store"]
        store.save("max_profile", CRED_MAX)

        resp = setup["client"].post("/profiles/max_profile/activate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["activated"] == "max_profile"

        # 크레덴셜이 실제로 교체됐는지 확인
        current = json.loads(
            setup["cred_file"].read_text(encoding="utf-8")
        )
        assert current["claudeAiOauth"]["subscriptionType"] == "max"

    def test_activate_nonexistent(self, setup):
        resp = setup["client"].post("/profiles/nonexistent/activate")
        assert resp.status_code == 404

    def test_activate_invalid_name(self, setup):
        resp = setup["client"].post("/profiles/_bad/activate")
        assert resp.status_code == 400


class TestDeleteProfile:
    def test_delete_existing(self, setup):
        setup["store"].save("to_delete", CRED_TEAM)

        resp = setup["client"].delete("/profiles/to_delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True

    def test_delete_nonexistent(self, setup):
        resp = setup["client"].delete("/profiles/ghost")
        assert resp.status_code == 404

    def test_delete_invalid_name(self, setup):
        resp = setup["client"].delete("/profiles/_bad")
        assert resp.status_code == 400
