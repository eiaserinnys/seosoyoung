"""
CredentialStore - 프로필별 크레덴셜 저장소

프로필별 credentials.json 저장/조회/삭제 및 활성 프로필 추적.
저장 경로: {profiles_dir}/{name}.json
활성 프로필 추적: {profiles_dir}/_active.txt
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 프로필 이름 유효성 패턴: 알파벳, 숫자, 하이픈, 언더스코어 (선두 언더스코어 제외)
_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")

# 프로필 이름 최대 길이 (NTFS 파일명 제한 고려)
_MAX_NAME_LENGTH = 64

# 내부 파일 이름 (프로필 목록에서 제외)
_INTERNAL_PREFIXES = ("_",)


class CredentialStore:
    """
    프로필별 크레덴셜 저장소.

    각 프로필은 {profiles_dir}/{name}.json 파일로 저장되며,
    활성 프로필은 {profiles_dir}/_active.txt 파일에 기록됩니다.
    """

    def __init__(self, profiles_dir: Path | str) -> None:
        self._dir = Path(profiles_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._active_file = self._dir / "_active.txt"

    @property
    def profiles_dir(self) -> Path:
        """프로필 저장 디렉토리 경로."""
        return self._dir

    def _validate_name(self, name: str) -> None:
        """프로필 이름 유효성 검사."""
        if (
            not name
            or len(name) > _MAX_NAME_LENGTH
            or not _VALID_NAME_RE.match(name)
        ):
            raise ValueError(
                f"유효하지 않은 프로필 이름: '{name}'. "
                "알파벳/숫자로 시작하고, 알파벳/숫자/하이픈/언더스코어만 허용됩니다. "
                f"(최대 {_MAX_NAME_LENGTH}자)"
            )

    def _profile_path(self, name: str) -> Path:
        return self._dir / f"{name}.json"

    def save(self, name: str, credentials: dict[str, Any]) -> Path:
        """
        프로필 저장.

        Args:
            name: 프로필 이름
            credentials: 크레덴셜 데이터 (claudeAiOauth 구조)

        Returns:
            저장된 파일 경로

        Raises:
            ValueError: 잘못된 프로필 이름
        """
        self._validate_name(name)
        path = self._profile_path(name)

        # 원자적 저장: 임시 파일 → rename
        tmp_path = path.with_suffix(".tmp")
        try:
            tmp_path.write_text(
                json.dumps(credentials, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # Windows에서 rename은 대상이 이미 있으면 실패하므로 replace 사용
            tmp_path.replace(path)
        except Exception:
            # 실패 시 임시 파일 정리
            tmp_path.unlink(missing_ok=True)
            raise

        logger.info(f"프로필 저장: {name}")
        return path

    def get(self, name: str) -> dict[str, Any] | None:
        """
        프로필 조회.

        Args:
            name: 프로필 이름

        Returns:
            크레덴셜 데이터 또는 None (없는 경우)

        Raises:
            ValueError: 잘못된 프로필 이름
        """
        self._validate_name(name)
        path = self._profile_path(name)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"프로필 읽기 실패: {name} - {e}")
            return None

    def delete(self, name: str) -> bool:
        """
        프로필 삭제.

        활성 프로필이면 활성 상태도 해제합니다.

        Args:
            name: 프로필 이름

        Returns:
            True: 삭제 성공, False: 프로필 없음

        Raises:
            ValueError: 잘못된 프로필 이름
        """
        self._validate_name(name)
        path = self._profile_path(name)
        if not path.is_file():
            return False

        path.unlink()
        logger.info(f"프로필 삭제: {name}")

        # 활성 프로필이었으면 해제
        if self.get_active() == name:
            self.clear_active()

        return True

    def set_active(self, name: str) -> None:
        """
        활성 프로필 설정.

        Args:
            name: 프로필 이름

        Raises:
            ValueError: 잘못된 프로필 이름
            FileNotFoundError: 프로필이 존재하지 않음
        """
        self._validate_name(name)
        if not self._profile_path(name).is_file():
            raise FileNotFoundError(f"프로필이 존재하지 않습니다: {name}")
        self._active_file.write_text(name, encoding="utf-8")
        logger.info(f"활성 프로필 설정: {name}")

    def get_active(self) -> str | None:
        """
        현재 활성 프로필 이름 조회.

        프로필 파일이 삭제된 경우 활성 상태를 자동으로 해제합니다.

        Returns:
            활성 프로필 이름 또는 None
        """
        if not self._active_file.is_file():
            return None
        text = self._active_file.read_text(encoding="utf-8").strip()
        if not text:
            return None
        # 프로필 파일이 삭제된 경우 활성 상태 해제
        if not self._profile_path(text).is_file():
            self.clear_active()
            return None
        return text

    def clear_active(self) -> None:
        """활성 프로필 해제."""
        self._active_file.unlink(missing_ok=True)
        logger.info("활성 프로필 해제")

    def list_profiles(self) -> list[dict[str, Any]]:
        """
        저장된 모든 프로필의 메타데이터 목록 조회.

        Returns:
            프로필 메타데이터 리스트 (이름, subscriptionType, rateLimitTier 등)
        """
        active = self.get_active()
        profiles: list[dict[str, Any]] = []

        for path in sorted(self._dir.glob("*.json")):
            # 내부 파일 제외
            if path.stem.startswith(_INTERNAL_PREFIXES):
                continue

            name = path.stem
            meta: dict[str, Any] = {
                "name": name,
                "is_active": name == active,
                "saved_at": path.stat().st_mtime,
            }

            # 크레덴셜에서 메타데이터 추출
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                oauth = data.get("claudeAiOauth", {})
                meta["subscriptionType"] = oauth.get("subscriptionType", "unknown")
                meta["rateLimitTier"] = oauth.get("rateLimitTier", "unknown")
                meta["expiresAt"] = oauth.get("expiresAt")
            except (json.JSONDecodeError, OSError):
                meta["subscriptionType"] = "unknown"
                meta["rateLimitTier"] = "unknown"
                meta["expiresAt"] = None

            profiles.append(meta)

        return profiles
