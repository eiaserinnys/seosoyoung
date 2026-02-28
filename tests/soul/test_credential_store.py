"""
test_credential_store - CredentialStore 단위 테스트

프로필별 크레덴셜 CRUD, 활성 프로필 추적, 메타데이터 조회.
"""

import json
from pathlib import Path

import pytest

from seosoyoung.soul.service.credential_store import CredentialStore


# 테스트용 크레덴셜 데이터 (실제 토큰 형식과 구분되는 fake 토큰 사용)
SAMPLE_CREDENTIAL = {
    "claudeAiOauth": {
        "accessToken": "fake-access-token-for-testing",
        "refreshToken": "fake-refresh-token-for-testing",
        "expiresAt": 1770300031040,
        "scopes": [
            "user:inference",
            "user:mcp_servers",
            "user:profile",
            "user:sessions:claude_code",
        ],
        "subscriptionType": "team",
        "rateLimitTier": "default_raven",
    }
}

SAMPLE_CREDENTIAL_MAX = {
    "claudeAiOauth": {
        "accessToken": "fake-max-access-token-for-testing",
        "refreshToken": "fake-max-refresh-token-for-testing",
        "expiresAt": 1772208817068,
        "scopes": [
            "user:inference",
            "user:mcp_servers",
            "user:profile",
            "user:sessions:claude_code",
        ],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_20x",
    }
}


@pytest.fixture
def store_dir(tmp_path: Path) -> Path:
    """임시 프로필 저장 디렉토리."""
    return tmp_path / "profiles"


@pytest.fixture
def store(store_dir: Path) -> CredentialStore:
    """테스트용 CredentialStore 인스턴스."""
    return CredentialStore(profiles_dir=store_dir)


class TestCredentialStoreInit:
    def test_creates_profiles_dir(self, store: CredentialStore, store_dir: Path):
        """프로필 디렉토리가 없으면 자동 생성."""
        assert store_dir.is_dir()

    def test_profiles_dir_already_exists(self, store_dir: Path):
        """이미 존재하는 디렉토리여도 에러 없이 초기화."""
        store_dir.mkdir(parents=True)
        store = CredentialStore(profiles_dir=store_dir)
        assert store_dir.is_dir()

    def test_profiles_dir_property(self, store: CredentialStore, store_dir: Path):
        """profiles_dir 프로퍼티가 올바른 경로 반환."""
        assert store.profiles_dir == store_dir


class TestSaveProfile:
    def test_save_creates_json_file(self, store: CredentialStore, store_dir: Path):
        """프로필 저장 시 JSON 파일 생성."""
        store.save("team_profile", SAMPLE_CREDENTIAL)
        path = store_dir / "team_profile.json"
        assert path.is_file()
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved["claudeAiOauth"]["subscriptionType"] == "team"

    def test_save_overwrites_existing(self, store: CredentialStore, store_dir: Path):
        """기존 프로필에 저장하면 덮어쓰기."""
        store.save("my_profile", SAMPLE_CREDENTIAL)
        store.save("my_profile", SAMPLE_CREDENTIAL_MAX)
        saved = json.loads(
            (store_dir / "my_profile.json").read_text(encoding="utf-8")
        )
        assert saved["claudeAiOauth"]["subscriptionType"] == "max"

    def test_save_invalid_name_raises(self, store: CredentialStore):
        """잘못된 프로필 이름은 거부."""
        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.save("../escape", SAMPLE_CREDENTIAL)

        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.save("", SAMPLE_CREDENTIAL)

        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.save("_active", SAMPLE_CREDENTIAL)

        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.save("_backup", SAMPLE_CREDENTIAL)

    def test_save_too_long_name_raises(self, store: CredentialStore):
        """64자 초과 이름은 거부."""
        long_name = "a" * 65
        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.save(long_name, SAMPLE_CREDENTIAL)

    def test_save_max_length_name_ok(self, store: CredentialStore):
        """64자 이름은 허용."""
        name = "a" * 64
        store.save(name, SAMPLE_CREDENTIAL)
        assert store.get(name) is not None


class TestGetProfile:
    def test_get_existing_profile(self, store: CredentialStore):
        """저장된 프로필 조회."""
        store.save("team", SAMPLE_CREDENTIAL)
        data = store.get("team")
        assert data is not None
        assert data["claudeAiOauth"]["subscriptionType"] == "team"

    def test_get_nonexistent_returns_none(self, store: CredentialStore):
        """없는 프로필 조회 시 None 반환."""
        assert store.get("nonexistent") is None

    def test_get_validates_name(self, store: CredentialStore):
        """get에서도 이름 유효성 검사."""
        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.get("_internal")

    def test_get_corrupted_profile_returns_none(
        self, store: CredentialStore, store_dir: Path
    ):
        """손상된 프로필 파일은 None 반환."""
        (store_dir / "broken.json").write_text("{invalid json", encoding="utf-8")
        assert store.get("broken") is None


class TestDeleteProfile:
    def test_delete_existing(self, store: CredentialStore, store_dir: Path):
        """프로필 삭제 시 파일 제거."""
        store.save("to_delete", SAMPLE_CREDENTIAL)
        assert (store_dir / "to_delete.json").is_file()

        result = store.delete("to_delete")
        assert result is True
        assert not (store_dir / "to_delete.json").exists()

    def test_delete_nonexistent_returns_false(self, store: CredentialStore):
        """없는 프로필 삭제 시 False."""
        assert store.delete("ghost") is False

    def test_delete_clears_active_if_was_active(self, store: CredentialStore):
        """활성 프로필을 삭제하면 활성 상태도 해제."""
        store.save("active_one", SAMPLE_CREDENTIAL)
        store.set_active("active_one")
        assert store.get_active() == "active_one"

        store.delete("active_one")
        assert store.get_active() is None

    def test_delete_validates_name(self, store: CredentialStore):
        """delete에서도 이름 유효성 검사."""
        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.delete("_internal")


class TestActiveProfile:
    def test_set_and_get_active(self, store: CredentialStore):
        """활성 프로필 설정/조회."""
        store.save("my_profile", SAMPLE_CREDENTIAL)
        store.set_active("my_profile")
        assert store.get_active() == "my_profile"

    def test_set_active_nonexistent_raises(self, store: CredentialStore):
        """존재하지 않는 프로필을 활성으로 설정하면 에러."""
        with pytest.raises(FileNotFoundError):
            store.set_active("nonexistent")

    def test_set_active_validates_name(self, store: CredentialStore):
        """set_active에서도 이름 유효성 검사."""
        with pytest.raises(ValueError, match="유효하지 않은 프로필 이름"):
            store.set_active("_internal")

    def test_get_active_when_none(self, store: CredentialStore):
        """활성 프로필이 없을 때 None."""
        assert store.get_active() is None

    def test_get_active_stale_profile_returns_none(
        self, store: CredentialStore, store_dir: Path
    ):
        """활성 프로필의 파일이 삭제되면 None 반환 및 자동 해제."""
        store.save("stale", SAMPLE_CREDENTIAL)
        store.set_active("stale")
        # 프로필 파일을 직접 삭제 (외부에서 삭제된 상황)
        (store_dir / "stale.json").unlink()

        assert store.get_active() is None
        # _active.txt도 정리됐는지 확인
        assert not (store_dir / "_active.txt").exists()

    def test_clear_active(self, store: CredentialStore):
        """활성 프로필 해제."""
        store.save("p", SAMPLE_CREDENTIAL)
        store.set_active("p")
        store.clear_active()
        assert store.get_active() is None


class TestListProfiles:
    def test_list_empty(self, store: CredentialStore):
        """프로필이 없으면 빈 리스트."""
        assert store.list_profiles() == []

    def test_list_with_profiles(self, store: CredentialStore):
        """프로필이 있으면 메타데이터 포함 리스트."""
        store.save("team", SAMPLE_CREDENTIAL)
        store.save("personal", SAMPLE_CREDENTIAL_MAX)

        profiles = store.list_profiles()
        assert len(profiles) == 2

        names = {p["name"] for p in profiles}
        assert names == {"team", "personal"}

    def test_list_contains_metadata(self, store: CredentialStore):
        """리스트 항목에 메타데이터 포함."""
        store.save("team", SAMPLE_CREDENTIAL)
        store.set_active("team")

        profiles = store.list_profiles()
        assert len(profiles) == 1

        p = profiles[0]
        assert p["name"] == "team"
        assert p["subscriptionType"] == "team"
        assert p["rateLimitTier"] == "default_raven"
        assert p["is_active"] is True
        assert "saved_at" in p

    def test_list_excludes_internal_files(
        self, store: CredentialStore, store_dir: Path
    ):
        """_active.txt, _backup.json 같은 내부 파일은 목록에 미포함."""
        store.save("real_profile", SAMPLE_CREDENTIAL)
        (store_dir / "_active.txt").write_text("real_profile", encoding="utf-8")
        (store_dir / "_backup.json").write_text("{}", encoding="utf-8")

        profiles = store.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "real_profile"

    def test_list_with_corrupted_file(
        self, store: CredentialStore, store_dir: Path
    ):
        """손상된 프로필 파일은 unknown 메타데이터로 표시."""
        (store_dir / "corrupted.json").write_text("{bad", encoding="utf-8")

        profiles = store.list_profiles()
        assert len(profiles) == 1
        p = profiles[0]
        assert p["name"] == "corrupted"
        assert p["subscriptionType"] == "unknown"
        assert p["rateLimitTier"] == "unknown"
        assert p["expiresAt"] is None
