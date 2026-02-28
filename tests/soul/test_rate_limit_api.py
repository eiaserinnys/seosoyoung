"""
test_rate_limit_api - Rate Limit REST API 통합 테스트

GET /profiles/rate-limits, GET /profiles/{name}/rate-limits 엔드포인트.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from seosoyoung.soul.service.credential_store import CredentialStore
from seosoyoung.soul.service.credential_swapper import CredentialSwapper
from seosoyoung.soul.service.rate_limit_tracker import RateLimitTracker
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


@pytest.fixture
def setup(tmp_path: Path):
    """테스트용 앱, 클라이언트, store, tracker를 셋업."""
    profiles_dir = tmp_path / "profiles"
    cred_dir = tmp_path / ".claude"
    cred_dir.mkdir()
    cred_file = cred_dir / ".credentials.json"
    cred_file.write_text(json.dumps(CRED_TEAM), encoding="utf-8")

    store = CredentialStore(profiles_dir=profiles_dir)
    swapper = CredentialSwapper(store=store, credentials_path=cred_file)
    tracker = RateLimitTracker(profiles_dir=profiles_dir)

    app = FastAPI()
    router = create_credentials_router(
        store=store, swapper=swapper, rate_limit_tracker=tracker
    )
    app.include_router(router, prefix="/profiles")

    client = TestClient(app)
    return {
        "client": client,
        "store": store,
        "tracker": tracker,
    }


class TestGetAllRateLimits:
    def test_empty_state(self, setup):
        """기록 없으면 빈 프로필 목록."""
        resp = setup["client"].get("/profiles/rate-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profiles"] == []
        assert data["active_profile"] is None

    def test_with_data(self, setup):
        """rate limit 기록 후 전체 조회."""
        tracker = setup["tracker"]
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("linegames", "five_hour", 0.55, future)
        tracker.record("linegames", "seven_day", 0.20, future)

        resp = setup["client"].get("/profiles/rate-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["profiles"]) == 1

        lg = data["profiles"][0]
        assert lg["name"] == "linegames"
        assert lg["five_hour"]["utilization"] == 0.55
        assert lg["seven_day"]["utilization"] == 0.20

    def test_with_active_profile(self, setup):
        """활성 프로필이 있을 때 active_profile 표시."""
        store = setup["store"]
        tracker = setup["tracker"]

        store.save("team", CRED_TEAM)
        store.set_active("team")

        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("team", "five_hour", 0.40, future)

        resp = setup["client"].get("/profiles/rate-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_profile"] == "team"


class TestGetProfileRateLimits:
    def test_known_profile(self, setup):
        """기록된 프로필의 rate limit 조회."""
        tracker = setup["tracker"]
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("linegames", "five_hour", 0.80, future)

        resp = setup["client"].get("/profiles/linegames/rate-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "linegames"
        assert data["five_hour"]["utilization"] == 0.80
        assert data["seven_day"]["utilization"] == "unknown"

    def test_unknown_profile(self, setup):
        """기록되지 않은 프로필은 unknown 상태."""
        resp = setup["client"].get("/profiles/unknown_profile/rate-limits")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "unknown_profile"
        assert data["five_hour"]["utilization"] == "unknown"
        assert data["seven_day"]["utilization"] == "unknown"


class TestNoTracker:
    """rate_limit_tracker가 None인 경우."""

    def test_rate_limits_501(self, tmp_path):
        """tracker 없으면 501 반환."""
        profiles_dir = tmp_path / "profiles"
        cred_file = tmp_path / ".claude" / ".credentials.json"
        cred_file.parent.mkdir()
        cred_file.write_text(json.dumps(CRED_TEAM), encoding="utf-8")

        store = CredentialStore(profiles_dir=profiles_dir)
        swapper = CredentialSwapper(store=store, credentials_path=cred_file)

        app = FastAPI()
        # rate_limit_tracker=None (기본값)
        router = create_credentials_router(store=store, swapper=swapper)
        app.include_router(router, prefix="/profiles")
        client = TestClient(app)

        resp = client.get("/profiles/rate-limits")
        assert resp.status_code == 501

    def test_profile_rate_limits_501(self, tmp_path):
        """tracker 없으면 개별 프로필도 501 반환."""
        profiles_dir = tmp_path / "profiles"
        cred_file = tmp_path / ".claude" / ".credentials.json"
        cred_file.parent.mkdir()
        cred_file.write_text(json.dumps(CRED_TEAM), encoding="utf-8")

        store = CredentialStore(profiles_dir=profiles_dir)
        swapper = CredentialSwapper(store=store, credentials_path=cred_file)

        app = FastAPI()
        router = create_credentials_router(store=store, swapper=swapper)
        app.include_router(router, prefix="/profiles")
        client = TestClient(app)

        resp = client.get("/profiles/linegames/rate-limits")
        assert resp.status_code == 501
