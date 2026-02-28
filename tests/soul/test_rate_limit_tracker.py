"""
test_rate_limit_tracker - RateLimitTracker 단위 테스트

프로필별 rate limit 상태 추적, 자동 리셋, 95% 알림, 영속화.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from seosoyoung.soul.service.rate_limit_tracker import RateLimitTracker


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    """임시 프로필 저장 디렉토리."""
    d = tmp_path / "profiles"
    d.mkdir()
    return d


@pytest.fixture
def tracker(profiles_dir: Path) -> RateLimitTracker:
    """테스트용 RateLimitTracker 인스턴스."""
    return RateLimitTracker(profiles_dir=profiles_dir)


class TestRecordRateLimit:
    """rate limit 이벤트 기록 테스트."""

    def test_record_five_hour(self, tracker: RateLimitTracker):
        """five_hour rate limit 기록."""
        resets_at = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record(
            profile="linegames",
            rate_limit_type="five_hour",
            utilization=0.51,
            resets_at=resets_at,
        )
        state = tracker.get_profile_state("linegames")
        assert state is not None
        assert state["five_hour"]["utilization"] == 0.51
        assert state["five_hour"]["resets_at"] == resets_at

    def test_record_seven_day(self, tracker: RateLimitTracker):
        """seven_day rate limit 기록."""
        resets_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        tracker.record(
            profile="personal",
            rate_limit_type="seven_day",
            utilization=0.30,
            resets_at=resets_at,
        )
        state = tracker.get_profile_state("personal")
        assert state is not None
        assert state["seven_day"]["utilization"] == 0.30
        assert state["seven_day"]["resets_at"] == resets_at

    def test_record_updates_existing(self, tracker: RateLimitTracker):
        """동일 프로필+타입 갱신 시 덮어쓰기."""
        resets_at = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("linegames", "five_hour", 0.30, resets_at)
        tracker.record("linegames", "five_hour", 0.55, resets_at)

        state = tracker.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == 0.55

    def test_record_multiple_types(self, tracker: RateLimitTracker):
        """동일 프로필에 여러 타입 기록."""
        resets_5h = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        resets_7d = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()

        tracker.record("linegames", "five_hour", 0.30, resets_5h)
        tracker.record("linegames", "seven_day", 0.10, resets_7d)

        state = tracker.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == 0.30
        assert state["seven_day"]["utilization"] == 0.10


class TestAutoReset:
    """resetsAt 시간 경과 시 자동 리셋 테스트."""

    def test_expired_resets_to_zero(self, tracker: RateLimitTracker):
        """만료된 rate limit는 utilization 0으로 처리."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        tracker.record("linegames", "five_hour", 0.80, past)

        state = tracker.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == 0.0

    def test_not_expired_keeps_value(self, tracker: RateLimitTracker):
        """아직 만료되지 않은 rate limit는 값 유지."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("linegames", "five_hour", 0.80, future)

        state = tracker.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == 0.80


class TestUnknownState:
    """알려지지 않은 프로필 상태 테스트."""

    def test_unknown_profile_returns_defaults(self, tracker: RateLimitTracker):
        """기록되지 않은 프로필은 unknown 상태 반환."""
        state = tracker.get_profile_state("unknown_profile")
        assert state is not None
        assert state["five_hour"]["utilization"] == "unknown"
        assert state["five_hour"]["resets_at"] is None
        assert state["seven_day"]["utilization"] == "unknown"
        assert state["seven_day"]["resets_at"] is None


class TestAlert95:
    """95% 알림 트리거 테스트."""

    def test_trigger_at_95(self, tracker: RateLimitTracker):
        """utilization >= 0.95에서 알림 트리거."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        alert = tracker.record("linegames", "five_hour", 0.95, future)
        assert alert is True

    def test_no_trigger_below_95(self, tracker: RateLimitTracker):
        """utilization < 0.95에서는 알림 없음."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        alert = tracker.record("linegames", "five_hour", 0.94, future)
        assert alert is False

    def test_no_duplicate_alert(self, tracker: RateLimitTracker):
        """동일 프로필+타입에 대해 한 번만 알림."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        alert1 = tracker.record("linegames", "five_hour", 0.95, future)
        alert2 = tracker.record("linegames", "five_hour", 0.97, future)

        assert alert1 is True
        assert alert2 is False

    def test_alert_resets_after_expiry(self, tracker: RateLimitTracker):
        """리셋 시간 이후에는 다시 알림 가능."""
        # 먼저 만료 예정인 시간으로 95% 기록
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        tracker.record("linegames", "five_hour", 0.95, past)

        # 리셋 후 새 기간에 다시 95% 도달
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        alert = tracker.record("linegames", "five_hour", 0.96, future)
        assert alert is True

    def test_separate_alerts_per_type(self, tracker: RateLimitTracker):
        """five_hour와 seven_day는 독립적으로 알림."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        alert_5h = tracker.record("linegames", "five_hour", 0.95, future)
        alert_7d = tracker.record("linegames", "seven_day", 0.96, future)

        assert alert_5h is True
        assert alert_7d is True

    def test_separate_alerts_per_profile(self, tracker: RateLimitTracker):
        """서로 다른 프로필은 독립적으로 알림."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        alert_lg = tracker.record("linegames", "five_hour", 0.95, future)
        alert_ps = tracker.record("personal", "five_hour", 0.96, future)

        assert alert_lg is True
        assert alert_ps is True


class TestPersistence:
    """JSON 파일 영속화 테스트."""

    def test_save_and_load(self, profiles_dir: Path):
        """저장 후 새 인스턴스에서 복원."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        tracker1 = RateLimitTracker(profiles_dir=profiles_dir)
        tracker1.record("linegames", "five_hour", 0.55, future)
        tracker1.save()

        # 새 인스턴스에서 로드
        tracker2 = RateLimitTracker(profiles_dir=profiles_dir)
        state = tracker2.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == 0.55

    def test_persistence_file_location(self, profiles_dir: Path):
        """영속화 파일이 올바른 위치에 생성."""
        tracker = RateLimitTracker(profiles_dir=profiles_dir)
        tracker.record(
            "linegames", "five_hour", 0.5,
            (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        )
        tracker.save()

        expected_path = profiles_dir / "_rate_limits.json"
        assert expected_path.is_file()

    def test_load_missing_file(self, profiles_dir: Path):
        """영속화 파일이 없으면 빈 상태로 시작."""
        tracker = RateLimitTracker(profiles_dir=profiles_dir)
        state = tracker.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == "unknown"

    def test_load_corrupted_file(self, profiles_dir: Path):
        """손상된 파일은 빈 상태로 시작."""
        (profiles_dir / "_rate_limits.json").write_text("{bad json", encoding="utf-8")
        tracker = RateLimitTracker(profiles_dir=profiles_dir)
        state = tracker.get_profile_state("linegames")
        assert state["five_hour"]["utilization"] == "unknown"

    def test_alert_flag_persisted(self, profiles_dir: Path):
        """95% 알림 플래그도 영속화."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

        tracker1 = RateLimitTracker(profiles_dir=profiles_dir)
        tracker1.record("linegames", "five_hour", 0.96, future)
        tracker1.save()

        tracker2 = RateLimitTracker(profiles_dir=profiles_dir)
        # 두 번째 인스턴스에서도 중복 알림 방지
        alert = tracker2.record("linegames", "five_hour", 0.97, future)
        assert alert is False


class TestGetAllStates:
    """전체 프로필 상태 조회 테스트."""

    def test_get_all_states(self, tracker: RateLimitTracker):
        """여러 프로필 상태를 한 번에 조회."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("linegames", "five_hour", 0.50, future)
        tracker.record("personal", "seven_day", 0.20, future)

        all_states = tracker.get_all_states()
        assert "linegames" in all_states
        assert "personal" in all_states
        assert all_states["linegames"]["five_hour"]["utilization"] == 0.50
        assert all_states["personal"]["seven_day"]["utilization"] == 0.20

    def test_get_all_states_empty(self, tracker: RateLimitTracker):
        """기록 없으면 빈 dict."""
        all_states = tracker.get_all_states()
        assert all_states == {}


class TestBuildCredentialAlert:
    """credential_alert SSE 이벤트 데이터 생성 테스트."""

    def test_build_alert_data(self, tracker: RateLimitTracker):
        """credential_alert 이벤트 데이터 구조."""
        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        tracker.record("linegames", "five_hour", 0.95, future)
        tracker.record("linegames", "seven_day", 0.51, future)
        tracker.record("personal", "five_hour", 0.0, None)

        alert_data = tracker.build_credential_alert(active_profile="linegames")

        assert alert_data["type"] == "credential_alert"
        assert alert_data["active_profile"] == "linegames"
        assert isinstance(alert_data["profiles"], list)
        assert len(alert_data["profiles"]) >= 1  # at least linegames

        # linegames 프로필 확인
        lg = next(p for p in alert_data["profiles"] if p["name"] == "linegames")
        assert lg["five_hour"]["utilization"] == 0.95
        assert lg["seven_day"]["utilization"] == 0.51
