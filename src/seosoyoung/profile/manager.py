"""Claude Code 인증 프로필 관리

~/.claude/.credentials.json 파일을 스왑하여 계정을 전환한다.
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProfileInfo:
    """프로필 정보"""

    name: str
    is_active: bool = False


_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*$")


class ProfileManager:
    """Claude Code 인증 프로필 관리자

    Args:
        profiles_dir: 프로필 저장 디렉토리 (.local/profiles/)
        credentials_path: Claude 인증 파일 경로 (~/.claude/.credentials.json)
    """

    def __init__(self, profiles_dir: Path, credentials_path: Path) -> None:
        self._profiles_dir = Path(profiles_dir)
        self._credentials_path = Path(credentials_path)

    def _validate_name(self, name: str) -> None:
        """프로필 이름 유효성 검증"""
        if not name:
            raise ValueError("프로필 이름이 비어 있습니다.")
        if name.startswith("_"):
            raise ValueError(f"'{name}'은(는) 예약된 접두사(_)를 사용합니다.")
        if not _NAME_PATTERN.match(name):
            raise ValueError(
                f"'{name}'은(는) 유효하지 않습니다. 영문, 숫자, 하이픈만 사용할 수 있습니다."
            )

    def _active_file(self) -> Path:
        return self._profiles_dir / "_active.txt"

    def _get_active_name(self) -> str | None:
        active_file = self._active_file()
        if active_file.exists():
            return active_file.read_text(encoding="utf-8").strip() or None
        return None

    def _set_active_name(self, name: str) -> None:
        self._active_file().write_text(name, encoding="utf-8")

    def _clear_active(self) -> None:
        active_file = self._active_file()
        if active_file.exists():
            active_file.unlink()

    def list_profiles(self) -> list[ProfileInfo]:
        """저장된 프로필 목록 반환 (활성 프로필 표시)"""
        if not self._profiles_dir.exists():
            return []

        active_name = self._get_active_name()
        profiles = []
        for f in sorted(self._profiles_dir.glob("*.json")):
            if f.name.startswith("_"):
                continue
            name = f.stem
            profiles.append(ProfileInfo(name=name, is_active=(name == active_name)))
        return profiles

    def save_profile(self, name: str) -> str:
        """현재 인증을 프로필로 저장

        Args:
            name: 프로필 이름

        Returns:
            결과 메시지

        Raises:
            ValueError: 이름이 유효하지 않을 때
            FileNotFoundError: 인증 파일이 없을 때
            FileExistsError: 동일 이름의 프로필이 이미 있을 때
        """
        self._validate_name(name)

        if not self._credentials_path.exists():
            raise FileNotFoundError(
                f"인증 파일을 찾을 수 없습니다: {self._credentials_path}"
            )

        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        profile_path = self._profiles_dir / f"{name}.json"
        if profile_path.exists():
            raise FileExistsError(f"프로필 '{name}'이(가) 이미 존재합니다.")

        shutil.copy2(self._credentials_path, profile_path)
        self._set_active_name(name)

        return f"프로필 '{name}'을(를) 저장했습니다."

    def change_profile(self, name: str) -> str:
        """저장된 프로필로 전환

        현재 인증을 _backup.json으로 백업한 후, 선택한 프로필로 교체한다.

        Args:
            name: 전환할 프로필 이름

        Returns:
            결과 메시지

        Raises:
            ValueError: 이름이 유효하지 않을 때
            FileNotFoundError: 프로필이 없을 때
        """
        self._validate_name(name)

        profile_path = self._profiles_dir / f"{name}.json"
        if not profile_path.exists():
            raise FileNotFoundError(f"프로필 '{name}'을(를) 찾을 수 없습니다.")

        # 현재 인증 백업
        if self._credentials_path.exists():
            backup_path = self._profiles_dir / "_backup.json"
            shutil.copy2(self._credentials_path, backup_path)

        # 프로필로 교체
        shutil.copy2(profile_path, self._credentials_path)
        self._set_active_name(name)

        return f"프로필 '{name}'(으)로 전환했습니다."

    def delete_profile(self, name: str) -> str:
        """프로필 삭제

        Args:
            name: 삭제할 프로필 이름

        Returns:
            결과 메시지

        Raises:
            ValueError: 이름이 유효하지 않을 때
            FileNotFoundError: 프로필이 없을 때
        """
        self._validate_name(name)

        profile_path = self._profiles_dir / f"{name}.json"
        if not profile_path.exists():
            raise FileNotFoundError(f"프로필 '{name}'을(를) 찾을 수 없습니다.")

        # 활성 프로필이면 active 해제
        if self._get_active_name() == name:
            self._clear_active()

        profile_path.unlink()
        return f"프로필 '{name}'을(를) 삭제했습니다."
