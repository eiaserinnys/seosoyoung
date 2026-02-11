"""ProfileManager 단위 테스트 (CLAUDE_CONFIG_DIR + Junction 방식)"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

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
        return ProfileManager(profiles_dir=tmp_path / "claude_profiles")

    def test_valid_names(self, manager):
        """영문, 숫자, 하이픈 조합은 허용"""
        for name in ["work", "personal-1", "my-team", "abc123"]:
            manager._validate_name(name)

    def test_underscore_prefix_rejected(self, manager):
        """_로 시작하는 이름은 예약어로 차단"""
        with pytest.raises(ValueError, match="예약"):
            manager._validate_name("_backup")

    def test_dot_prefix_rejected(self, manager):
        """.으로 시작하는 이름은 예약어로 차단"""
        with pytest.raises(ValueError, match="예약"):
            manager._validate_name(".shared")

    def test_invalid_characters_rejected(self, manager):
        """특수문자 포함 이름 차단"""
        for name in ["work space", "a/b", "hello!", "한글"]:
            with pytest.raises(ValueError, match="영문"):
                manager._validate_name(name)

    def test_empty_name_rejected(self, manager):
        """빈 이름 차단"""
        with pytest.raises(ValueError):
            manager._validate_name("")


class TestDirectoryStructure:
    """디렉토리 구조 테스트"""

    @pytest.fixture
    def manager(self, tmp_path):
        return ProfileManager(profiles_dir=tmp_path / "claude_profiles")

    def test_profiles_dir_property(self, manager, tmp_path):
        assert manager.profiles_dir == tmp_path / "claude_profiles"

    def test_shared_dir(self, manager, tmp_path):
        assert manager._shared_dir == tmp_path / "claude_profiles" / ".shared"

    def test_active_file(self, manager, tmp_path):
        assert manager._active_file() == tmp_path / "claude_profiles" / "_active.txt"

    def test_profile_dir(self, manager, tmp_path):
        assert manager._profile_dir("work") == tmp_path / "claude_profiles" / "work"


class TestGetActiveProfile:
    """활성 프로필 조회 테스트"""

    @pytest.fixture
    def manager(self, tmp_path):
        mgr = ProfileManager(profiles_dir=tmp_path / "claude_profiles")
        mgr.profiles_dir.mkdir(parents=True, exist_ok=True)
        return mgr

    def test_no_active_file_returns_none(self, manager):
        assert manager._get_active_name() is None

    def test_empty_active_file_returns_none(self, manager):
        manager._active_file().write_text("", encoding="utf-8")
        assert manager._get_active_name() is None

    def test_reads_active_name(self, manager):
        manager._active_file().write_text("work", encoding="utf-8")
        assert manager._get_active_name() == "work"


class TestListProfiles:
    """list_profiles 테스트"""

    @pytest.fixture
    def manager(self, tmp_path):
        return ProfileManager(profiles_dir=tmp_path / "claude_profiles")

    def test_empty_list_when_no_dir(self, manager):
        result = manager.list_profiles()
        assert result == []

    def test_lists_profile_directories(self, manager):
        base = manager.profiles_dir
        base.mkdir(parents=True, exist_ok=True)

        # 프로필 디렉토리 생성 (credentials.json이 있는 폴더만 프로필)
        (base / "work").mkdir()
        (base / "work" / ".credentials.json").write_text('{}', encoding="utf-8")
        (base / "personal").mkdir()
        (base / "personal" / ".credentials.json").write_text('{}', encoding="utf-8")

        result = manager.list_profiles()
        names = [p.name for p in result]
        assert sorted(names) == ["personal", "work"]

    def test_active_profile_marked(self, manager):
        base = manager.profiles_dir
        base.mkdir(parents=True, exist_ok=True)

        (base / "work").mkdir()
        (base / "work" / ".credentials.json").write_text('{}', encoding="utf-8")
        (base / "personal").mkdir()
        (base / "personal" / ".credentials.json").write_text('{}', encoding="utf-8")

        (base / "_active.txt").write_text("work", encoding="utf-8")

        result = manager.list_profiles()
        active = [p for p in result if p.is_active]
        assert len(active) == 1
        assert active[0].name == "work"

    def test_ignores_hidden_and_reserved_dirs(self, manager):
        """_나 .으로 시작하는 디렉토리는 제외"""
        base = manager.profiles_dir
        base.mkdir(parents=True, exist_ok=True)

        # 예약 디렉토리
        (base / ".shared").mkdir()
        (base / "_active.txt").write_text("", encoding="utf-8")

        # 정상 프로필
        (base / "work").mkdir()
        (base / "work" / ".credentials.json").write_text('{}', encoding="utf-8")

        result = manager.list_profiles()
        assert len(result) == 1
        assert result[0].name == "work"

    def test_ignores_dirs_without_credentials(self, manager):
        """credentials.json 없는 디렉토리는 프로필로 인식하지 않음"""
        base = manager.profiles_dir
        base.mkdir(parents=True, exist_ok=True)

        (base / "incomplete").mkdir()  # credentials 없음

        result = manager.list_profiles()
        assert len(result) == 0


class TestSaveProfile:
    """save_profile 테스트"""

    @pytest.fixture
    def setup(self, tmp_path):
        """기존 .claude 폴더 시뮬레이션"""
        source_claude_dir = tmp_path / "source_claude"
        source_claude_dir.mkdir()
        (source_claude_dir / ".credentials.json").write_text(
            json.dumps({"token": "my-secret-token"}), encoding="utf-8"
        )
        (source_claude_dir / "settings.json").write_text(
            json.dumps({"theme": "dark"}), encoding="utf-8"
        )
        # 공유 대상 폴더
        (source_claude_dir / "projects").mkdir()
        (source_claude_dir / "projects" / "test.json").write_text('{}', encoding="utf-8")
        (source_claude_dir / "todos").mkdir()
        (source_claude_dir / "plans").mkdir()

        profiles_dir = tmp_path / "claude_profiles"
        mgr = ProfileManager(profiles_dir=profiles_dir)
        return mgr, source_claude_dir

    def test_save_creates_profile_directory(self, setup):
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        profile_dir = mgr._profile_dir("work")
        assert profile_dir.is_dir()

    def test_save_copies_credentials(self, setup):
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        cred = mgr._profile_dir("work") / ".credentials.json"
        assert cred.exists()
        data = json.loads(cred.read_text(encoding="utf-8"))
        assert data["token"] == "my-secret-token"

    def test_save_copies_settings(self, setup):
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        settings = mgr._profile_dir("work") / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text(encoding="utf-8"))
        assert data["theme"] == "dark"

    def test_save_initializes_shared_dir(self, setup):
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        shared = mgr._shared_dir
        assert (shared / "projects").is_dir()
        assert (shared / "todos").is_dir()
        assert (shared / "plans").is_dir()

    def test_save_moves_shared_data_to_shared_dir(self, setup):
        """첫 프로필 저장 시 소스의 공유 데이터가 .shared로 이동"""
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        shared = mgr._shared_dir
        # 소스의 projects 내용이 .shared/projects로 복사되었는지
        assert (shared / "projects" / "test.json").exists()

    def test_save_creates_junctions(self, setup):
        """프로필 디렉토리에 Junction 생성 확인"""
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        profile_dir = mgr._profile_dir("work")
        for dirname in ["projects", "todos", "plans"]:
            junction_path = profile_dir / dirname
            assert junction_path.is_dir(), f"{dirname} junction이 없음"

    def test_save_updates_active(self, setup):
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)

        assert mgr._get_active_name() == "work"

    def test_save_duplicate_raises(self, setup):
        mgr, source_dir = setup
        mgr.save_profile("work", source_dir)
        with pytest.raises(FileExistsError):
            mgr.save_profile("work", source_dir)

    def test_save_no_credentials_raises(self, tmp_path):
        mgr = ProfileManager(profiles_dir=tmp_path / "claude_profiles")
        empty_dir = tmp_path / "empty_claude"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="인증 파일"):
            mgr.save_profile("work", empty_dir)

    def test_save_returns_message(self, setup):
        mgr, source_dir = setup
        result = mgr.save_profile("work", source_dir)
        assert isinstance(result, str)
        assert "work" in result


class TestChangeProfile:
    """change_profile 테스트 (활성 프로필 변경)"""

    @pytest.fixture
    def setup(self, tmp_path):
        source_dir = tmp_path / "source_claude"
        source_dir.mkdir()
        (source_dir / ".credentials.json").write_text(
            json.dumps({"token": "work-token"}), encoding="utf-8"
        )
        (source_dir / "settings.json").write_text('{}', encoding="utf-8")
        for d in ["projects", "todos", "plans"]:
            (source_dir / d).mkdir()

        profiles_dir = tmp_path / "claude_profiles"
        mgr = ProfileManager(profiles_dir=profiles_dir)
        mgr.save_profile("work", source_dir)

        # personal 프로필도 생성
        (source_dir / ".credentials.json").write_text(
            json.dumps({"token": "personal-token"}), encoding="utf-8"
        )
        mgr.save_profile("personal", source_dir)

        return mgr

    def test_change_updates_active(self, setup):
        mgr = setup
        mgr.change_profile("work")
        assert mgr._get_active_name() == "work"

    def test_change_nonexistent_raises(self, setup):
        mgr = setup
        with pytest.raises(FileNotFoundError):
            mgr.change_profile("nonexistent")

    def test_change_returns_message(self, setup):
        mgr = setup
        result = mgr.change_profile("work")
        assert isinstance(result, str)
        assert "work" in result


class TestGetConfigDir:
    """get_config_dir 테스트 (CLAUDE_CONFIG_DIR 경로 반환)"""

    @pytest.fixture
    def setup(self, tmp_path):
        source_dir = tmp_path / "source_claude"
        source_dir.mkdir()
        (source_dir / ".credentials.json").write_text('{}', encoding="utf-8")
        (source_dir / "settings.json").write_text('{}', encoding="utf-8")
        for d in ["projects", "todos", "plans"]:
            (source_dir / d).mkdir()

        profiles_dir = tmp_path / "claude_profiles"
        mgr = ProfileManager(profiles_dir=profiles_dir)
        mgr.save_profile("work", source_dir)
        return mgr

    def test_returns_profile_dir_path(self, setup):
        mgr = setup
        config_dir = mgr.get_config_dir("work")
        assert config_dir == mgr._profile_dir("work")
        assert config_dir.is_dir()

    def test_nonexistent_raises(self, setup):
        mgr = setup
        with pytest.raises(FileNotFoundError):
            mgr.get_config_dir("nonexistent")

    def test_get_active_config_dir(self, setup):
        """활성 프로필의 config dir 반환"""
        mgr = setup
        config_dir = mgr.get_active_config_dir()
        assert config_dir == mgr._profile_dir("work")

    def test_no_active_returns_none(self, tmp_path):
        mgr = ProfileManager(profiles_dir=tmp_path / "claude_profiles")
        assert mgr.get_active_config_dir() is None


class TestDeleteProfile:
    """delete_profile 테스트"""

    @pytest.fixture
    def setup(self, tmp_path):
        source_dir = tmp_path / "source_claude"
        source_dir.mkdir()
        (source_dir / ".credentials.json").write_text('{}', encoding="utf-8")
        (source_dir / "settings.json").write_text('{}', encoding="utf-8")
        for d in ["projects", "todos", "plans"]:
            (source_dir / d).mkdir()

        profiles_dir = tmp_path / "claude_profiles"
        mgr = ProfileManager(profiles_dir=profiles_dir)
        mgr.save_profile("work", source_dir)

        (source_dir / ".credentials.json").write_text('{"token":"p"}', encoding="utf-8")
        mgr.save_profile("personal", source_dir)

        return mgr

    def test_delete_removes_profile_dir(self, setup):
        mgr = setup
        profile_dir = mgr._profile_dir("work")
        assert profile_dir.exists()

        mgr.delete_profile("work")
        assert not profile_dir.exists()

    def test_delete_clears_active_if_active(self, setup):
        """활성 프로필을 삭제하면 active 해제"""
        mgr = setup
        mgr.change_profile("work")
        assert mgr._get_active_name() == "work"

        mgr.delete_profile("work")
        assert mgr._get_active_name() is None

    def test_delete_keeps_active_if_different(self, setup):
        """다른 프로필 삭제 시 active 유지"""
        mgr = setup
        # personal이 active (마지막 save)
        assert mgr._get_active_name() == "personal"

        mgr.delete_profile("work")
        assert mgr._get_active_name() == "personal"

    def test_delete_preserves_shared_dir(self, setup):
        """프로필 삭제해도 .shared는 유지"""
        mgr = setup
        mgr.delete_profile("work")
        assert mgr._shared_dir.is_dir()

    def test_delete_nonexistent_raises(self, setup):
        mgr = setup
        with pytest.raises(FileNotFoundError):
            mgr.delete_profile("nonexistent")

    def test_delete_returns_message(self, setup):
        mgr = setup
        result = mgr.delete_profile("work")
        assert isinstance(result, str)
        assert "work" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
