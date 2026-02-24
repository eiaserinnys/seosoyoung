"""Claude Code 인증 프로필 관리 (CLAUDE_CONFIG_DIR + Junction 방식)

각 프로필은 독립된 디렉토리로 관리되며, CLAUDE_CONFIG_DIR 환경변수로 지정된다.
세션 히스토리(projects/, todos/, plans/)는 .shared/ 폴더에 원본을 두고
각 프로필 디렉토리에 Windows Junction으로 연결하여 공유한다.
"""

import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SHARED_DIRS = ["projects", "todos", "plans"]
PROFILE_FILES = [".credentials.json", "settings.json"]


@dataclass
class ProfileInfo:
    """프로필 정보"""

    name: str
    is_active: bool = False


_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*$")


class ProfileManager:
    """Claude Code 인증 프로필 관리자 (CLAUDE_CONFIG_DIR + Junction)

    디렉토리 구조:
        profiles_dir/
        ├── .shared/              ← 공유 데이터 원본
        │   ├── projects/
        │   ├── todos/
        │   └── plans/
        ├── _active.txt           ← 활성 프로필 이름
        ├── work/                 ← 프로필 폴더 (CLAUDE_CONFIG_DIR로 지정)
        │   ├── .credentials.json
        │   ├── settings.json
        │   ├── projects/         ← Junction → .shared/projects
        │   ├── todos/            ← Junction → .shared/todos
        │   └── plans/            ← Junction → .shared/plans
        └── personal/             ← 동일 구조

    Args:
        profiles_dir: 프로필 저장 디렉토리 (.local/claude_profiles/)
    """

    def __init__(self, profiles_dir: Path) -> None:
        self._profiles_dir = Path(profiles_dir)

    @property
    def profiles_dir(self) -> Path:
        return self._profiles_dir

    @property
    def _shared_dir(self) -> Path:
        return self._profiles_dir / ".shared"

    def _validate_name(self, name: str) -> None:
        if not name:
            raise ValueError("프로필 이름이 비어 있습니다.")
        if name.startswith("_") or name.startswith("."):
            raise ValueError(f"'{name}'은(는) 예약된 접두사를 사용합니다.")
        if not _NAME_PATTERN.match(name):
            raise ValueError(
                f"'{name}'은(는) 유효하지 않습니다. 영문, 숫자, 하이픈만 사용할 수 있습니다."
            )

    def _active_file(self) -> Path:
        return self._profiles_dir / "_active.txt"

    def _profile_dir(self, name: str) -> Path:
        return self._profiles_dir / name

    def _get_active_name(self) -> str | None:
        active_file = self._active_file()
        if active_file.exists():
            return active_file.read_text(encoding="utf-8").strip() or None
        return None

    def _set_active_name(self, name: str) -> None:
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._active_file().write_text(name, encoding="utf-8")

    def _clear_active(self) -> None:
        active_file = self._active_file()
        if active_file.exists():
            active_file.unlink()

    def _ensure_shared_dir(self, source_dir: Path | None = None) -> None:
        """공유 디렉토리 초기화. source_dir에서 기존 데이터를 복사."""
        shared = self._shared_dir
        for dirname in SHARED_DIRS:
            shared_sub = shared / dirname
            if not shared_sub.exists():
                shared_sub.mkdir(parents=True, exist_ok=True)
                # 소스에서 기존 데이터 복사
                if source_dir:
                    source_sub = source_dir / dirname
                    if source_sub.is_dir():
                        shutil.copytree(source_sub, shared_sub, dirs_exist_ok=True)

    def _create_junction(self, link_path: Path, target_path: Path) -> None:
        """Windows Junction 생성 (mklink /J)"""
        if link_path.exists():
            return

        link_str = str(link_path)
        target_str = str(target_path.resolve())

        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", link_str, target_str],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Junction 생성 실패: {link_str} → {target_str}: {e}")
            raise

    def _setup_junctions(self, profile_dir: Path) -> None:
        """프로필 디렉토리에 공유 디렉토리 Junction 생성"""
        shared = self._shared_dir
        for dirname in SHARED_DIRS:
            link_path = profile_dir / dirname
            target_path = shared / dirname
            self._create_junction(link_path, target_path)

    def _remove_junctions(self, profile_dir: Path) -> None:
        """프로필 디렉토리의 Junction 제거 (rmdir로 Junction만 제거, 원본 보존)"""
        for dirname in SHARED_DIRS:
            link_path = profile_dir / dirname
            if link_path.exists():
                try:
                    # Junction은 rmdir로 제거해야 원본이 보존됨
                    subprocess.run(
                        ["cmd", "/c", "rmdir", str(link_path)],
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError:
                    logger.warning(f"Junction 제거 실패: {link_path}")

    def list_profiles(self) -> list[ProfileInfo]:
        """저장된 프로필 목록 반환"""
        if not self._profiles_dir.exists():
            return []

        active_name = self._get_active_name()
        profiles = []
        for entry in sorted(self._profiles_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue
            # .credentials.json 있는 디렉토리만 프로필
            if not (entry / ".credentials.json").exists():
                continue
            profiles.append(
                ProfileInfo(name=entry.name, is_active=(entry.name == active_name))
            )
        return profiles

    def save_profile(self, name: str, source_dir: Path) -> str:
        """프로필 저장 (소스 디렉토리에서 인증 정보 복사 + Junction 설정)

        Args:
            name: 프로필 이름
            source_dir: 소스 Claude 설정 디렉토리 (~/.claude)

        Returns:
            결과 메시지
        """
        self._validate_name(name)
        source_dir = Path(source_dir)

        cred_source = source_dir / ".credentials.json"
        if not cred_source.exists():
            raise FileNotFoundError(
                f"인증 파일을 찾을 수 없습니다: {cred_source}"
            )

        profile_dir = self._profile_dir(name)
        if profile_dir.exists():
            raise FileExistsError(f"프로필 '{name}'이(가) 이미 존재합니다.")

        # 프로필 디렉토리 생성
        profile_dir.mkdir(parents=True, exist_ok=True)

        # 프로필 고유 파일 복사
        for filename in PROFILE_FILES:
            src = source_dir / filename
            if src.exists():
                shutil.copy2(src, profile_dir / filename)

        # 공유 디렉토리 초기화 (첫 프로필 저장 시 소스에서 데이터 복사)
        self._ensure_shared_dir(source_dir)

        # Junction 생성
        self._setup_junctions(profile_dir)

        # 활성 프로필 설정
        self._set_active_name(name)

        return f"프로필 '{name}'을(를) 저장했습니다."

    def change_profile(self, name: str) -> str:
        """활성 프로필 변경 (재시작 시 CLAUDE_CONFIG_DIR이 이 프로필을 가리킴)

        Args:
            name: 전환할 프로필 이름

        Returns:
            결과 메시지
        """
        self._validate_name(name)

        profile_dir = self._profile_dir(name)
        if not profile_dir.exists():
            raise FileNotFoundError(f"프로필 '{name}'을(를) 찾을 수 없습니다.")

        self._set_active_name(name)
        return f"프로필 '{name}'(으)로 전환했습니다. 재시작 후 적용됩니다."

    def get_config_dir(self, name: str) -> Path:
        """프로필의 CLAUDE_CONFIG_DIR 경로 반환

        Args:
            name: 프로필 이름

        Returns:
            프로필 디렉토리 경로

        Raises:
            FileNotFoundError: 프로필이 없을 때
        """
        self._validate_name(name)

        profile_dir = self._profile_dir(name)
        if not profile_dir.exists():
            raise FileNotFoundError(f"프로필 '{name}'을(를) 찾을 수 없습니다.")
        return profile_dir

    def get_active_config_dir(self) -> Path | None:
        """활성 프로필의 CLAUDE_CONFIG_DIR 경로 반환. 없으면 None."""
        active_name = self._get_active_name()
        if not active_name:
            return None
        try:
            return self.get_config_dir(active_name)
        except (FileNotFoundError, ValueError):
            return None

    def delete_profile(self, name: str) -> str:
        """프로필 삭제

        Args:
            name: 삭제할 프로필 이름

        Returns:
            결과 메시지
        """
        self._validate_name(name)

        profile_dir = self._profile_dir(name)
        if not profile_dir.exists():
            raise FileNotFoundError(f"프로필 '{name}'을(를) 찾을 수 없습니다.")

        # 활성 프로필이면 active 해제
        if self._get_active_name() == name:
            self._clear_active()

        # Junction 먼저 제거 (원본 보존)
        self._remove_junctions(profile_dir)

        # 프로필 디렉토리 삭제
        shutil.rmtree(profile_dir)

        return f"프로필 '{name}'을(를) 삭제했습니다."
