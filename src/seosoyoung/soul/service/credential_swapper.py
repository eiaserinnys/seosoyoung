"""
CredentialSwapper - 크레덴셜 파일 교체 모듈

~/.claude/.credentials.json 파일을 프로필별로 교체합니다.
- 현재 활성 크레덴셜을 프로필로 저장 (save)
- 지정된 프로필의 크레덴셜로 교체 (activate)
- 원자적 교체 (임시 파일 → rename)
"""

import json
import logging
from pathlib import Path
from typing import Any

from seosoyoung.soul.service.credential_store import CredentialStore

logger = logging.getLogger(__name__)


class CredentialSwapper:
    """
    크레덴셜 파일 교체기.

    credentials_path의 파일을 읽고 쓰며,
    CredentialStore를 통해 프로필 저장/조회/활성 추적을 처리합니다.
    """

    def __init__(
        self,
        store: CredentialStore,
        credentials_path: Path | str,
    ) -> None:
        self._store = store
        self._cred_path = Path(credentials_path)

    def read_current(self) -> dict[str, Any]:
        """
        현재 크레덴셜 파일을 읽어 반환.

        Returns:
            크레덴셜 데이터

        Raises:
            FileNotFoundError: 크레덴셜 파일이 없음
        """
        if not self._cred_path.is_file():
            raise FileNotFoundError(
                f"크레덴셜 파일이 존재하지 않습니다: {self._cred_path}"
            )
        return json.loads(self._cred_path.read_text(encoding="utf-8"))

    def save_current_as(self, name: str) -> None:
        """
        현재 크레덴셜을 프로필로 저장.

        Args:
            name: 프로필 이름

        Raises:
            FileNotFoundError: 크레덴셜 파일이 없음
            ValueError: 잘못된 프로필 이름
        """
        data = self.read_current()
        self._store.save(name, data)
        self._store.set_active(name)
        logger.info(f"현재 크레덴셜을 프로필 '{name}'으로 저장")

    def activate(self, name: str) -> None:
        """
        지정된 프로필의 크레덴셜로 교체.

        1. 프로필 데이터 조회
        2. 현재 크레덴셜 백업 ({profiles_dir}/_backup.json) — 원자적 쓰기
        3. 원자적 교체 (임시 파일 → rename)
        4. 활성 프로필 갱신

        Args:
            name: 프로필 이름

        Raises:
            FileNotFoundError: 프로필이 존재하지 않음
        """
        # 1. 프로필 데이터 조회
        data = self._store.get(name)
        if data is None:
            raise FileNotFoundError(f"프로필이 존재하지 않습니다: {name}")

        # 2. 현재 크레덴셜 원자적 백업
        if self._cred_path.is_file():
            backup_path = self._store.profiles_dir / "_backup.json"
            backup_tmp = backup_path.with_suffix(".tmp")
            try:
                current = self._cred_path.read_text(encoding="utf-8")
                backup_tmp.write_text(current, encoding="utf-8")
                backup_tmp.replace(backup_path)
            except Exception:
                backup_tmp.unlink(missing_ok=True)
                raise

        # 3. 원자적 교체
        new_content = json.dumps(data, ensure_ascii=False)
        tmp_path = self._cred_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(new_content, encoding="utf-8")
            tmp_path.replace(self._cred_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        # 4. 활성 프로필 갱신
        self._store.set_active(name)
        logger.info(f"프로필 '{name}' 활성화 완료")
