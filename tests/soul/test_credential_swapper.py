"""
test_credential_swapper - CredentialSwapper 단위 테스트

크레덴셜 파일 교체(원자적), 백업, 활성 프로필 추적 연동.
"""

import json
from pathlib import Path

import pytest

from seosoyoung.soul.service.credential_store import CredentialStore
from seosoyoung.soul.service.credential_swapper import CredentialSwapper


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
def profiles_dir(tmp_path: Path) -> Path:
    return tmp_path / "profiles"


@pytest.fixture
def credentials_file(tmp_path: Path) -> Path:
    """~/.claude/.credentials.json 을 흉내내는 임시 파일."""
    cred_dir = tmp_path / ".claude"
    cred_dir.mkdir()
    cred_file = cred_dir / ".credentials.json"
    cred_file.write_text(json.dumps(CRED_TEAM), encoding="utf-8")
    return cred_file


@pytest.fixture
def store(profiles_dir: Path) -> CredentialStore:
    return CredentialStore(profiles_dir=profiles_dir)


@pytest.fixture
def swapper(
    store: CredentialStore, credentials_file: Path
) -> CredentialSwapper:
    return CredentialSwapper(store=store, credentials_path=credentials_file)


class TestSaveCurrentAsProfile:
    def test_save_current_credentials(
        self, swapper: CredentialSwapper, store: CredentialStore
    ):
        """현재 크레덴셜을 프로필로 저장."""
        swapper.save_current_as("team_profile")

        data = store.get("team_profile")
        assert data is not None
        assert data["claudeAiOauth"]["subscriptionType"] == "team"

    def test_save_sets_active(
        self, swapper: CredentialSwapper, store: CredentialStore
    ):
        """저장 후 해당 프로필이 활성 상태."""
        swapper.save_current_as("team_profile")
        assert store.get_active() == "team_profile"

    def test_save_when_credentials_missing(
        self, store: CredentialStore, tmp_path: Path
    ):
        """크레덴셜 파일이 없으면 에러."""
        missing = tmp_path / "no" / "such" / "file.json"
        swapper = CredentialSwapper(store=store, credentials_path=missing)

        with pytest.raises(FileNotFoundError):
            swapper.save_current_as("test")


class TestActivateProfile:
    def test_activate_swaps_credentials(
        self, swapper: CredentialSwapper, credentials_file: Path, store: CredentialStore
    ):
        """프로필 활성화 시 크레덴셜 파일이 교체됨."""
        # 먼저 max 프로필을 저장소에 넣어둠
        store.save("max_profile", CRED_MAX)

        swapper.activate("max_profile")

        # 크레덴셜 파일이 max로 교체됐는지 확인
        current = json.loads(credentials_file.read_text(encoding="utf-8"))
        assert current["claudeAiOauth"]["subscriptionType"] == "max"

    def test_activate_sets_active(
        self, swapper: CredentialSwapper, store: CredentialStore
    ):
        """활성화 후 store의 활성 프로필이 갱신."""
        store.save("max_profile", CRED_MAX)
        swapper.activate("max_profile")
        assert store.get_active() == "max_profile"

    def test_activate_creates_backup(
        self, swapper: CredentialSwapper, store: CredentialStore, profiles_dir: Path
    ):
        """활성화 전에 현재 크레덴셜을 백업."""
        store.save("max_profile", CRED_MAX)
        swapper.activate("max_profile")

        backup_path = profiles_dir / "_backup.json"
        assert backup_path.is_file()

        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        assert backup["claudeAiOauth"]["subscriptionType"] == "team"

    def test_activate_nonexistent_raises(self, swapper: CredentialSwapper):
        """없는 프로필 활성화 시 에러."""
        with pytest.raises(FileNotFoundError):
            swapper.activate("nonexistent")

    def test_activate_is_atomic(
        self, swapper: CredentialSwapper, store: CredentialStore, credentials_file: Path
    ):
        """교체 중 임시 파일이 남지 않음."""
        store.save("max_profile", CRED_MAX)
        swapper.activate("max_profile")

        # 임시 파일(.tmp)이 남아있지 않아야 함
        tmp_files = list(credentials_file.parent.glob("*.tmp"))
        assert len(tmp_files) == 0


class TestReadCurrent:
    def test_read_current_credentials(
        self, swapper: CredentialSwapper
    ):
        """현재 크레덴셜 읽기."""
        data = swapper.read_current()
        assert data["claudeAiOauth"]["subscriptionType"] == "team"

    def test_read_when_file_missing(
        self, store: CredentialStore, tmp_path: Path
    ):
        """파일이 없을 때 에러."""
        missing = tmp_path / "no_file.json"
        swapper = CredentialSwapper(store=store, credentials_path=missing)

        with pytest.raises(FileNotFoundError):
            swapper.read_current()


class TestActivateRoundTrip:
    def test_save_activate_roundtrip(
        self, swapper: CredentialSwapper, credentials_file: Path, store: CredentialStore
    ):
        """저장 → 다른 프로필 활성화 → 원래 프로필 복원 라운드트립."""
        # 현재(team)를 저장
        swapper.save_current_as("team_saved")

        # max 프로필 등록
        store.save("max_saved", CRED_MAX)

        # max로 전환
        swapper.activate("max_saved")
        current = json.loads(credentials_file.read_text(encoding="utf-8"))
        assert current["claudeAiOauth"]["subscriptionType"] == "max"

        # team으로 복원
        swapper.activate("team_saved")
        current = json.loads(credentials_file.read_text(encoding="utf-8"))
        assert current["claudeAiOauth"]["subscriptionType"] == "team"
