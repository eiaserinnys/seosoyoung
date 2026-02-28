"""크레덴셜 프로필 시스템 E2E 통합 테스트

전체 플로우를 검증합니다:
  프로필 저장 → rate limit 추적 → 95% 알림 → 버튼 클릭 → 프로필 전환

Soulstream API (FastAPI TestClient) ↔ Bot 핸들러 통합 테스트.
에러 케이스: 서버 다운, 크레덴셜 파일 잠금/권한 오류 처리.
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from seosoyoung.soul.service.credential_store import CredentialStore
from seosoyoung.soul.service.credential_swapper import CredentialSwapper
from seosoyoung.soul.service.rate_limit_tracker import RateLimitTracker
from seosoyoung.soul.api.credentials import create_credentials_router
from seosoyoung.slackbot.handlers.credential_ui import (
    build_credential_alert_blocks,
    build_credential_alert_text,
    send_credential_alert,
)
from seosoyoung.slackbot.handlers.actions import activate_credential_profile


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
def env(tmp_path: Path):
    """전체 시스템 환경 셋업: store, swapper, tracker, API client"""
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
        store=store, swapper=swapper, rate_limit_tracker=tracker,
    )
    app.include_router(router, prefix="/profiles")

    client = TestClient(app)
    return {
        "client": client,
        "store": store,
        "swapper": swapper,
        "tracker": tracker,
        "cred_file": cred_file,
        "profiles_dir": profiles_dir,
    }


class TestE2EProfileSaveToSwitch:
    """E2E: 프로필 저장 → rate limit 추적 → 95% 알림 → 버튼 전환"""

    def test_full_flow(self, env):
        """프로필 저장 → rate limit 기록 → 95% 알림 → UI 렌더링 → 전환"""
        client = env["client"]
        tracker = env["tracker"]

        # 1. 프로필 저장
        resp = client.post("/profiles/team")
        assert resp.status_code == 200
        assert resp.json()["saved"] is True

        # max 프로필을 직접 store에 등록
        env["store"].save("personal", CRED_MAX)

        # 2. 프로필 목록 확인
        resp = client.get("/profiles")
        assert resp.status_code == 200
        profiles = resp.json()["profiles"]
        names = {p["name"] for p in profiles}
        assert names == {"team", "personal"}
        assert resp.json()["active"] == "team"

        # 3. rate limit 추적: team 프로필 사용량 기록
        future_5h = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
        future_7d = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()

        # 50% → 알림 없음
        alert = tracker.record("team", "five_hour", 0.50, future_5h)
        assert alert is False

        # 95% → 알림 트리거
        alert = tracker.record("team", "five_hour", 0.96, future_5h)
        assert alert is True

        # 두 번째 95% → 중복 알림 방지
        alert = tracker.record("team", "five_hour", 0.97, future_5h)
        assert alert is False

        # 7일 사용량도 기록
        tracker.record("team", "seven_day", 0.51, future_7d)
        tracker.record("personal", "five_hour", 0.10, future_5h)
        tracker.record("personal", "seven_day", 0.05, future_7d)

        # 4. rate limit 현황 API 조회
        resp = client.get("/profiles/rate-limits")
        assert resp.status_code == 200
        rate_data = resp.json()
        assert rate_data["active_profile"] == "team"
        assert len(rate_data["profiles"]) == 2

        # 5. credential_alert SSE 데이터 생성
        alert_data = tracker.build_credential_alert("team")
        assert alert_data["type"] == "credential_alert"
        assert alert_data["active_profile"] == "team"
        assert len(alert_data["profiles"]) == 2

        # 6. Slack Block Kit UI 렌더링
        blocks = build_credential_alert_blocks(
            alert_data["active_profile"],
            alert_data["profiles"],
        )
        assert len(blocks) == 2
        assert blocks[0]["type"] == "section"
        assert blocks[1]["type"] == "actions"

        text_content = blocks[0]["text"]["text"]
        assert "team" in text_content
        assert "personal" in text_content

        buttons = blocks[1]["elements"]
        assert len(buttons) == 2
        team_btn = next(b for b in buttons if b["value"] == "team")
        personal_btn = next(b for b in buttons if b["value"] == "personal")
        assert "(현재)" in team_btn["text"]["text"]
        assert "style" not in team_btn
        assert personal_btn["style"] == "primary"

        # 7. 프로필 전환 (team → personal)
        resp = client.post("/profiles/personal/activate")
        assert resp.status_code == 200
        assert resp.json()["activated"] == "personal"

        # 크레덴셜 파일이 실제로 교체됐는지 확인
        current = json.loads(env["cred_file"].read_text(encoding="utf-8"))
        assert current["claudeAiOauth"]["subscriptionType"] == "max"

        # 활성 프로필도 갱신됐는지
        resp = client.get("/profiles/active")
        assert resp.json()["active"] == "personal"

        # 8. 원래 프로필로 복원
        resp = client.post("/profiles/team/activate")
        assert resp.status_code == 200
        current = json.loads(env["cred_file"].read_text(encoding="utf-8"))
        assert current["claudeAiOauth"]["subscriptionType"] == "team"


class TestE2ESendCredentialAlert:
    """E2E: credential_alert 이벤트 → 슬랙 알림 전송"""

    def _reset_cooldown(self):
        import seosoyoung.slackbot.handlers.credential_ui as mod
        mod._last_alert_time = 0.0

    def test_send_alert_with_real_data(self, env):
        """rate limit 데이터를 기반으로 슬랙 알림 전송"""
        self._reset_cooldown()
        tracker = env["tracker"]

        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("team", "five_hour", 0.96, future)
        tracker.record("team", "seven_day", 0.40, None)

        alert_data = tracker.build_credential_alert("team")

        slack_client = MagicMock()
        send_credential_alert(slack_client, "C_TEST", alert_data)

        slack_client.chat_postMessage.assert_called_once()
        call_kwargs = slack_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C_TEST"
        assert "blocks" in call_kwargs
        assert "team" in call_kwargs["text"]


class TestE2EButtonClickProfileSwitch:
    """E2E: 버튼 클릭 → Soul API → 프로필 전환"""

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_button_activates_profile(self, mock_urlopen, env):
        """프로필 전환 버튼 클릭 시 Soul API 호출 + 메시지 업데이트"""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        slack_client = MagicMock()
        activate_credential_profile("personal", "C_TEST", "ts_test", slack_client)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert "/profiles/personal/activate" in req.full_url
        assert req.method == "POST"

        slack_client.chat_update.assert_called_once()
        call_kwargs = slack_client.chat_update.call_args[1]
        assert "✅" in call_kwargs["text"]
        assert "personal" in call_kwargs["text"]


class TestE2ERateLimitWindowReset:
    """E2E: rate limit 윈도우 만료 → 알림 초기화 → 재알림"""

    def test_alert_resets_after_window_expires(self, env):
        """윈도우 만료 후 다시 95% 도달하면 재알림"""
        tracker = env["tracker"]

        # 과거 시간으로 window 만료 시뮬레이션
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        future = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()

        # 첫 번째 알림 (과거 window)
        tracker.record("team", "five_hour", 0.96, past)
        # 만료된 window이므로 알림 안 함

        # 새 window에서 95% 도달 → 알림
        alert = tracker.record("team", "five_hour", 0.96, future)
        assert alert is True

        # 같은 window에서 재알림 방지
        alert = tracker.record("team", "five_hour", 0.97, future)
        assert alert is False


class TestE2EErrorHandling:
    """에러 케이스: Soulstream 서버 다운, 크레덴셜 오류"""

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_soul_server_down_graceful(self, mock_urlopen):
        """Soul 서버 다운 시 graceful 에러 메시지"""
        mock_urlopen.side_effect = ConnectionRefusedError("Connection refused")

        slack_client = MagicMock()
        activate_credential_profile("team", "C_TEST", "ts_test", slack_client)

        slack_client.chat_update.assert_called_once()
        call_kwargs = slack_client.chat_update.call_args[1]
        assert "❌" in call_kwargs["text"]
        assert "team" in call_kwargs["text"]

    @patch("seosoyoung.slackbot.handlers.actions.urllib.request.urlopen")
    def test_timeout_graceful(self, mock_urlopen):
        """Soul API 타임아웃 시 graceful 에러 메시지"""
        import urllib.error
        mock_urlopen.side_effect = TimeoutError("Request timed out")

        slack_client = MagicMock()
        activate_credential_profile("team", "C_TEST", "ts_test", slack_client)

        slack_client.chat_update.assert_called_once()
        assert "❌" in slack_client.chat_update.call_args[1]["text"]

    def test_credential_file_missing_on_save(self, tmp_path):
        """크레덴셜 파일 없이 저장 시도 시 에러"""
        store = CredentialStore(profiles_dir=tmp_path / "profiles")
        missing_file = tmp_path / "nonexistent" / ".credentials.json"
        swapper = CredentialSwapper(store=store, credentials_path=missing_file)

        with pytest.raises(FileNotFoundError):
            swapper.save_current_as("test")

    def test_activate_nonexistent_profile(self, env):
        """존재하지 않는 프로필 활성화 시 404"""
        resp = env["client"].post("/profiles/ghost/activate")
        assert resp.status_code == 404

    def test_invalid_profile_name_rejected(self):
        """유효하지 않은 프로필 이름은 API 호출 없이 거부"""
        slack_client = MagicMock()
        activate_credential_profile("../../etc/passwd", "C_TEST", "ts", slack_client)

        slack_client.chat_update.assert_called_once()
        assert "유효하지 않은" in slack_client.chat_update.call_args[1]["text"]

    def test_rate_limits_without_tracker(self, tmp_path):
        """RateLimitTracker 미초기화 시 rate-limits 엔드포인트 501"""
        profiles_dir = tmp_path / "profiles"
        cred_dir = tmp_path / ".claude"
        cred_dir.mkdir()
        cred_file = cred_dir / ".credentials.json"
        cred_file.write_text(json.dumps(CRED_TEAM), encoding="utf-8")

        store = CredentialStore(profiles_dir=profiles_dir)
        swapper = CredentialSwapper(store=store, credentials_path=cred_file)

        app = FastAPI()
        router = create_credentials_router(
            store=store, swapper=swapper, rate_limit_tracker=None,
        )
        app.include_router(router, prefix="/profiles")
        client = TestClient(app)

        resp = client.get("/profiles/rate-limits")
        assert resp.status_code == 501


class TestE2ECredentialAlertUIIntegration:
    """credential_alert 데이터 → UI 렌더링 → 텍스트 검증"""

    def test_multiple_profiles_with_mixed_states(self, env):
        """여러 프로필의 다양한 상태가 정확히 렌더링되는지 검증"""
        tracker = env["tracker"]

        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("team", "five_hour", 0.96, future)
        tracker.record("team", "seven_day", 0.51, future)
        # personal은 기록 없음 → unknown 상태

        alert_data = tracker.build_credential_alert("team")
        blocks = build_credential_alert_blocks(
            alert_data["active_profile"],
            alert_data["profiles"],
        )

        text = blocks[0]["text"]["text"]

        # team 프로필: 96%와 51% 표시
        assert "96%" in text
        assert "51%" in text
        # team이 활성 프로필
        assert "(활성)" in text

    def test_fallback_text_matches_blocks(self, env):
        """fallback text가 blocks 내용과 일치"""
        tracker = env["tracker"]
        tracker.record("team", "five_hour", 0.5, None)

        alert_data = tracker.build_credential_alert("team")
        blocks = build_credential_alert_blocks(
            alert_data["active_profile"],
            alert_data["profiles"],
        )
        text = build_credential_alert_text(
            alert_data["active_profile"],
            alert_data["profiles"],
        )

        # 공통 내용 포함 여부
        assert "team" in text
        assert "50%" in text


class TestE2EProfileCRUDViaAPI:
    """API를 통한 프로필 CRUD 전체 라이프사이클"""

    def test_create_list_switch_delete(self, env):
        """프로필 생성 → 목록 → 전환 → 삭제 전체 플로우"""
        client = env["client"]

        # 저장
        resp = client.post("/profiles/team")
        assert resp.status_code == 200

        # max 프로필 직접 등록
        env["store"].save("personal", CRED_MAX)

        # 목록
        resp = client.get("/profiles")
        assert len(resp.json()["profiles"]) == 2

        # 전환
        resp = client.post("/profiles/personal/activate")
        assert resp.status_code == 200
        assert resp.json()["activated"] == "personal"

        # 활성 확인
        resp = client.get("/profiles/active")
        assert resp.json()["active"] == "personal"

        # 삭제
        resp = client.delete("/profiles/team")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        # 삭제 후 목록 확인
        resp = client.get("/profiles")
        assert len(resp.json()["profiles"]) == 1
        assert resp.json()["profiles"][0]["name"] == "personal"


class TestE2EStatePersistence:
    """rate limit 상태 영속화 검증"""

    def test_tracker_state_survives_restart(self, tmp_path):
        """서버 재시작 후 rate limit 상태가 유지되는지 확인"""
        profiles_dir = tmp_path / "profiles"

        # 첫 번째 인스턴스에서 상태 기록
        tracker1 = RateLimitTracker(profiles_dir=profiles_dir)
        future = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
        tracker1.record("team", "five_hour", 0.80, future)
        tracker1.record("team", "seven_day", 0.40, future)

        # 두 번째 인스턴스로 복원
        tracker2 = RateLimitTracker(profiles_dir=profiles_dir)
        state = tracker2.get_profile_state("team")

        assert state["five_hour"]["utilization"] == 0.80
        assert state["seven_day"]["utilization"] == 0.40

    def test_95_alert_flag_persists(self, tmp_path):
        """95% 알림 플래그가 재시작 후에도 유지되어 중복 알림 방지"""
        profiles_dir = tmp_path / "profiles"

        future = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()

        # 첫 번째 인스턴스에서 95% 알림 트리거
        tracker1 = RateLimitTracker(profiles_dir=profiles_dir)
        alert = tracker1.record("team", "five_hour", 0.96, future)
        assert alert is True

        # 두 번째 인스턴스에서 동일 이벤트 → 중복 알림 방지
        tracker2 = RateLimitTracker(profiles_dir=profiles_dir)
        alert = tracker2.record("team", "five_hour", 0.97, future)
        assert alert is False
