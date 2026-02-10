"""관찰 로그 저장소

파일 기반으로 사용자별 관찰 로그와 세션별 대화 로그를 관리합니다.

저장 구조:
    memory/
    ├── observations/
    │   ├── {user_id}.md          # 관찰 로그 (마크다운)
    │   └── {user_id}.meta.json   # 메타데이터
    ├── pending/
    │   └── {user_id}.jsonl       # 미관찰 대화 버퍼 (누적)
    └── conversations/
        └── {thread_ts}.jsonl     # 세션별 대화 로그
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

logger = logging.getLogger(__name__)


@dataclass
class MemoryRecord:
    """사용자별 관찰 로그 레코드"""

    user_id: str
    username: str = ""
    observations: str = ""
    observation_tokens: int = 0
    last_observed_at: datetime | None = None
    total_sessions_observed: int = 0
    reflection_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_meta_dict(self) -> dict:
        """메타데이터를 직렬화 가능한 dict로 변환"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "observation_tokens": self.observation_tokens,
            "last_observed_at": (
                self.last_observed_at.isoformat() if self.last_observed_at else None
            ),
            "total_sessions_observed": self.total_sessions_observed,
            "reflection_count": self.reflection_count,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_meta_dict(cls, data: dict, observations: str = "") -> "MemoryRecord":
        """dict에서 MemoryRecord를 복원"""
        last_observed = data.get("last_observed_at")
        created = data.get("created_at")
        return cls(
            user_id=data["user_id"],
            username=data.get("username", ""),
            observations=observations,
            observation_tokens=data.get("observation_tokens", 0),
            last_observed_at=(
                datetime.fromisoformat(last_observed) if last_observed else None
            ),
            total_sessions_observed=data.get("total_sessions_observed", 0),
            reflection_count=data.get("reflection_count", 0),
            created_at=(
                datetime.fromisoformat(created)
                if created
                else datetime.now(timezone.utc)
            ),
        )


class MemoryStore:
    """파일 기반 관찰 로그 저장소"""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.observations_dir = self.base_dir / "observations"
        self.pending_dir = self.base_dir / "pending"
        self.conversations_dir = self.base_dir / "conversations"

    def _ensure_dirs(self) -> None:
        """저장소 디렉토리가 없으면 생성"""
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(parents=True, exist_ok=True)

    def _obs_path(self, user_id: str) -> Path:
        return self.observations_dir / f"{user_id}.md"

    def _meta_path(self, user_id: str) -> Path:
        return self.observations_dir / f"{user_id}.meta.json"

    def _lock_path(self, user_id: str) -> Path:
        return self.observations_dir / f"{user_id}.lock"

    def _conv_path(self, thread_ts: str) -> Path:
        return self.conversations_dir / f"{thread_ts}.jsonl"

    def get_record(self, user_id: str) -> MemoryRecord | None:
        """사용자의 관찰 레코드를 로드합니다. 없으면 None."""
        meta_path = self._meta_path(user_id)
        if not meta_path.exists():
            return None

        lock = FileLock(str(self._lock_path(user_id)), timeout=5)
        with lock:
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))

            obs_path = self._obs_path(user_id)
            observations = ""
            if obs_path.exists():
                observations = obs_path.read_text(encoding="utf-8")

            return MemoryRecord.from_meta_dict(meta_data, observations)

    def save_record(self, record: MemoryRecord) -> None:
        """관찰 레코드를 저장합니다."""
        self._ensure_dirs()

        lock = FileLock(str(self._lock_path(record.user_id)), timeout=5)
        with lock:
            # 관찰 로그 (마크다운)
            self._obs_path(record.user_id).write_text(
                record.observations, encoding="utf-8"
            )

            # 메타데이터 (JSON)
            self._meta_path(record.user_id).write_text(
                json.dumps(record.to_meta_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _pending_path(self, user_id: str) -> Path:
        return self.pending_dir / f"{user_id}.jsonl"

    def _pending_lock_path(self, user_id: str) -> Path:
        return self.pending_dir / f"{user_id}.lock"

    def append_pending_messages(self, user_id: str, messages: list[dict]) -> None:
        """미관찰 대화를 사용자별 버퍼에 누적합니다."""
        self._ensure_dirs()

        lock = FileLock(str(self._pending_lock_path(user_id)), timeout=5)
        with lock:
            with open(self._pending_path(user_id), "a", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def load_pending_messages(self, user_id: str) -> list[dict]:
        """미관찰 대화 버퍼를 로드합니다. 없으면 빈 리스트."""
        pending_path = self._pending_path(user_id)
        if not pending_path.exists():
            return []

        lock = FileLock(str(self._pending_lock_path(user_id)), timeout=5)
        with lock:
            messages = []
            with open(pending_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
            return messages

    def clear_pending_messages(self, user_id: str) -> None:
        """관찰 완료 후 미관찰 대화 버퍼를 비웁니다."""
        pending_path = self._pending_path(user_id)
        if pending_path.exists():
            lock = FileLock(str(self._pending_lock_path(user_id)), timeout=5)
            with lock:
                pending_path.unlink()

    def save_conversation(self, thread_ts: str, messages: list[dict]) -> None:
        """세션 대화 로그를 JSONL로 저장합니다."""
        self._ensure_dirs()

        conv_path = self._conv_path(thread_ts)
        with open(conv_path, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def load_conversation(self, thread_ts: str) -> list[dict] | None:
        """세션 대화 로그를 로드합니다. 없으면 None."""
        conv_path = self._conv_path(thread_ts)
        if not conv_path.exists():
            return None

        messages = []
        with open(conv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages
