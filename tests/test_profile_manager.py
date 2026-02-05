"""ProfileManager 단위 테스트"""

import json
import tempfile
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from seosoyoung.profile.manager import ProfileManager, ProfileInfo


class TestProfileInfo:
    """ProfileInfo 데이터클래스 테스트"""

    def test_creation(self):
        info = ProfileInfo(name="work", is_active=True)
        assert info.name == "work"
        assert info.is_active is True

    def test_inactive_by_default(self):
        info = ProfileInfo(name="personal")
        assert info.is_active is False


class TestProfileNameValidation:
    """프로필 이름 유효성 검증 테스트"""

    @pytest.fixture
    def manager(self, tmp_path):
        credentials = tmp_path / "credentials.json"
        credentials.write_text('{"token": "test"}', encoding="utf-8")
        return ProfileManager(
            profiles_dir=tmp_path / "profiles",
            credentials_path=credentials,
        )

    def test_valid_names(self, manager):
        """영문, 숫자, 하이픈 조합은 허용"""
        for name in ["work", "personal-1", "my-team", "abc123"]:
            manager._validate_name(name)  # 예외 없으면 통과

    def test_underscore_prefix_rejected(self, manager):
        """_로 시작하는 이름은 예약어로 차단"""
        with pytest.raises(ValueError, match="예약"):
            manager._validate_name("_backup")

    def test_invalid_characters_rejected(self, manager):
        """특수문자 포함 이름 차단"""
        for name in ["work space", "a/b", "hello!", "한글"]:
            with pytest.raises(ValueError, match="영문"):
                manager._validate_name(name)

    def test_empty_name_rejected(self, manager):
        """빈 이름 차단"""
        with pytest.raises(ValueError):
            manager._validate_name("")


class TestProfileManagerSave:
    """save_profile 테스트"""

    @pytest.fixture
    def setup(self, tmp_path):
        cred_path = tmp_path / "credentials.json"
        cred_path.write_text(
            json.dumps({"token": "my-secret-token"}), encoding="utf-8"
        )
        profiles_dir = tmp_path / "profiles"
        mgr = ProfileManager(
            profiles_dir=profiles_dir, credentials_path=cred_path
        )
        return mgr, profiles_dir, cred_path

    def test_save_creates_profile_file(self, setup):
        mgr, profiles_dir, _ = setup
        mgr.save_profile("work")

        saved = profiles_dir / "work.json"
        assert saved.exists()
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert data["token"] == "my-secret-token"

    def test_save_updates_active_txt(self, setup):
        mgr, profiles_dir, _ = setup
        mgr.save_profile("work")

        active_file = profiles_dir / "_active.txt"
        assert active_file.exists()
        assert active_file.read_text(encoding="utf-8").strip() == "work"

    def test_save_duplicate_name_raises(self, setup):
        mgr, _, _ = setup
        mgr.save_profile("work")
        with pytest.raises(FileExistsError):
            mgr.save_profile("work")

    def test_save_no_credentials_raises(self, tmp_path):
        """인증 파일이 없으면 에러"""
        mgr = ProfileManager(
            profiles_dir=tmp_path / "profiles",
            credentials_path=tmp_path / "nonexistent.json",
        )
        with pytest.raises(FileNotFoundError):
            mgr.save_profile("work")

    def test_save_returns_message(self, setup):
        mgr, _, _ = setup
        result = mgr.save_profile("work")
        assert isinstance(result, str)
        assert "work" in result


class TestProfileManagerList:
    """list_profiles 테스트"""

    @pytest.fixture
    def setup(self, tmp_path):
        cred_path = tmp_path / "credentials.json"
        cred_path.write_text('{"token": "test"}', encoding="utf-8")
        profiles_dir = tmp_path / "profiles"
        mgr = ProfileManager(
            profiles_dir=profiles_dir, credentials_path=cred_path
        )
        return mgr, profiles_dir

    def test_empty_list(self, setup):
        mgr, _ = setup
        result = mgr.list_profiles()
        assert result == []

    def test_list_with_profiles(self, setup):
        mgr, profiles_dir = setup
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "work.json").write_text('{"token":"a"}', encoding="utf-8")
        (profiles_dir / "personal.json").write_text('{"token":"b"}', encoding="utf-8")

        result = mgr.list_profiles()
        names = [p.name for p in result]
        assert sorted(names) == ["personal", "work"]

    def test_active_profile_marked(self, setup):
        mgr, _ = setup
        mgr.save_profile("work")
        mgr.save_profile("personal")
        # work를 저장한 뒤 personal을 저장하면 active가 personal

        result = mgr.list_profiles()
        active = [p for p in result if p.is_active]
        assert len(active) == 1
        assert active[0].name == "personal"

    def test_ignores_underscore_files(self, setup):
        """_로 시작하는 파일은 목록에서 제외"""
        mgr, profiles_dir = setup
        profiles_dir.mkdir(parents=True, exist_ok=True)
        (profiles_dir / "_active.txt").write_text("work", encoding="utf-8")
        (profiles_dir / "_backup.json").write_text('{}', encoding="utf-8")
        (profiles_dir / "work.json").write_text('{"token":"a"}', encoding="utf-8")

        result = mgr.list_profiles()
        assert len(result) == 1
        assert result[0].name == "work"


class TestProfileManagerChange:
    """change_profile 테스트"""

    @pytest.fixture
    def setup(self, tmp_path):
        cred_path = tmp_path / "credentials.json"
        cred_path.write_text(
            json.dumps({"token": "original-token"}), encoding="utf-8"
        )
        profiles_dir = tmp_path / "profiles"
        mgr = ProfileManager(
            profiles_dir=profiles_dir, credentials_path=cred_path
        )
        return mgr, profiles_dir, cred_path

    def test_change_swaps_credentials(self, setup):
        mgr, profiles_dir, cred_path = setup
        # 프로필 저장
        mgr.save_profile("work")

        # 새 인증으로 변경
        cred_path.write_text(
            json.dumps({"token": "new-token"}), encoding="utf-8"
        )
        mgr.save_profile("personal")

        # work로 전환
        mgr.change_profile("work")

        data = json.loads(cred_path.read_text(encoding="utf-8"))
        assert data["token"] == "original-token"

    def test_change_creates_backup(self, setup):
        mgr, profiles_dir, cred_path = setup
        mgr.save_profile("work")

        # 인증을 변경하고 다시 전환
        cred_path.write_text(
            json.dumps({"token": "current-token"}), encoding="utf-8"
        )
        mgr.change_profile("work")

        backup = profiles_dir / "_backup.json"
        assert backup.exists()
        backup_data = json.loads(backup.read_text(encoding="utf-8"))
        assert backup_data["token"] == "current-token"

    def test_change_updates_active_txt(self, setup):
        mgr, profiles_dir, _ = setup
        mgr.save_profile("work")
        mgr.save_profile("personal")

        mgr.change_profile("work")

        active = (profiles_dir / "_active.txt").read_text(encoding="utf-8").strip()
        assert active == "work"

    def test_change_nonexistent_raises(self, setup):
        mgr, _, _ = setup
        with pytest.raises(FileNotFoundError):
            mgr.change_profile("nonexistent")

    def test_change_returns_message(self, setup):
        mgr, _, _ = setup
        mgr.save_profile("work")
        result = mgr.change_profile("work")
        assert isinstance(result, str)
        assert "work" in result


class TestProfileManagerDelete:
    """delete_profile 테스트"""

    @pytest.fixture
    def setup(self, tmp_path):
        cred_path = tmp_path / "credentials.json"
        cred_path.write_text('{"token": "test"}', encoding="utf-8")
        profiles_dir = tmp_path / "profiles"
        mgr = ProfileManager(
            profiles_dir=profiles_dir, credentials_path=cred_path
        )
        return mgr, profiles_dir

    def test_delete_removes_file(self, setup):
        mgr, profiles_dir = setup
        mgr.save_profile("work")
        assert (profiles_dir / "work.json").exists()

        mgr.delete_profile("work")
        assert not (profiles_dir / "work.json").exists()

    def test_delete_clears_active_if_active(self, setup):
        """활성 프로필을 삭제하면 _active.txt도 삭제"""
        mgr, profiles_dir = setup
        mgr.save_profile("work")

        mgr.delete_profile("work")
        active_file = profiles_dir / "_active.txt"
        assert not active_file.exists()

    def test_delete_keeps_active_if_different(self, setup):
        """다른 프로필이 활성일 때 삭제해도 active 유지"""
        mgr, profiles_dir = setup
        mgr.save_profile("work")
        mgr.save_profile("personal")  # personal이 active

        mgr.delete_profile("work")

        active = (profiles_dir / "_active.txt").read_text(encoding="utf-8").strip()
        assert active == "personal"

    def test_delete_nonexistent_raises(self, setup):
        mgr, _ = setup
        with pytest.raises(FileNotFoundError):
            mgr.delete_profile("nonexistent")

    def test_delete_returns_message(self, setup):
        mgr, _ = setup
        mgr.save_profile("work")
        result = mgr.delete_profile("work")
        assert isinstance(result, str)
        assert "work" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
