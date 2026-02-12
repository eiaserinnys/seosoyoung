"""관찰 로그 저장소

파일 기반으로 세션(thread_ts) 단위 관찰 로그, 대화 로그, 장기 기억을 관리합니다.

저장 구조:
    memory/
    ├── observations/
    │   ├── {thread_ts}.md          # 세션별 관찰 로그 (마크다운)
    │   ├── {thread_ts}.meta.json   # 메타데이터 (user_id 포함)
    │   └── {thread_ts}.inject      # OM 주입 플래그 (존재하면 다음 요청에 주입)
    ├── pending/
    │   └── {thread_ts}.jsonl       # 세션별 미관찰 대화 버퍼 (누적)
    ├── conversations/
    │   └── {thread_ts}.jsonl       # 세션별 대화 로그
    ├── candidates/
    │   └── {thread_ts}.jsonl       # 장기 기억 후보 (세션 단위 누적)
    └── persistent/
        ├── recent.md               # 활성 장기 기억
        ├── recent.meta.json        # 메타데이터
        └── archive/                # 컴팩션 시 이전 버전 보존
            └── recent_{timestamp}.md
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
    """세션별 관찰 로그 레코드

    thread_ts를 기본 키로 사용하고, user_id는 메타데이터로 보관합니다.
    """

    thread_ts: str
    user_id: str = ""
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
            "thread_ts": self.thread_ts,
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
            thread_ts=data.get("thread_ts", ""),
            user_id=data.get("user_id", ""),
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
    """파일 기반 관찰 로그 저장소

    세션(thread_ts)을 기본 키로 사용합니다.
    """

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.observations_dir = self.base_dir / "observations"
        self.pending_dir = self.base_dir / "pending"
        self.conversations_dir = self.base_dir / "conversations"
        self.candidates_dir = self.base_dir / "candidates"
        self.persistent_dir = self.base_dir / "persistent"

    def _ensure_dirs(self) -> None:
        """저장소 디렉토리가 없으면 생성"""
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.candidates_dir.mkdir(parents=True, exist_ok=True)
        self.persistent_dir.mkdir(parents=True, exist_ok=True)

    def _obs_path(self, thread_ts: str) -> Path:
        return self.observations_dir / f"{thread_ts}.md"

    def _meta_path(self, thread_ts: str) -> Path:
        return self.observations_dir / f"{thread_ts}.meta.json"

    def _lock_path(self, thread_ts: str) -> Path:
        return self.observations_dir / f"{thread_ts}.lock"

    def _conv_path(self, thread_ts: str) -> Path:
        return self.conversations_dir / f"{thread_ts}.jsonl"

    def get_record(self, thread_ts: str) -> MemoryRecord | None:
        """세션의 관찰 레코드를 로드합니다. 없으면 None."""
        meta_path = self._meta_path(thread_ts)
        if not meta_path.exists():
            return None

        lock = FileLock(str(self._lock_path(thread_ts)), timeout=5)
        with lock:
            meta_data = json.loads(meta_path.read_text(encoding="utf-8"))

            obs_path = self._obs_path(thread_ts)
            observations = ""
            if obs_path.exists():
                observations = obs_path.read_text(encoding="utf-8")

            return MemoryRecord.from_meta_dict(meta_data, observations)

    def save_record(self, record: MemoryRecord) -> None:
        """관찰 레코드를 저장합니다."""
        self._ensure_dirs()

        lock = FileLock(str(self._lock_path(record.thread_ts)), timeout=5)
        with lock:
            # 관찰 로그 (마크다운)
            self._obs_path(record.thread_ts).write_text(
                record.observations, encoding="utf-8"
            )

            # 메타데이터 (JSON)
            self._meta_path(record.thread_ts).write_text(
                json.dumps(record.to_meta_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def _pending_path(self, thread_ts: str) -> Path:
        return self.pending_dir / f"{thread_ts}.jsonl"

    def _pending_lock_path(self, thread_ts: str) -> Path:
        return self.pending_dir / f"{thread_ts}.lock"

    def append_pending_messages(self, thread_ts: str, messages: list[dict]) -> None:
        """미관찰 대화를 세션별 버퍼에 누적합니다."""
        self._ensure_dirs()

        lock = FileLock(str(self._pending_lock_path(thread_ts)), timeout=5)
        with lock:
            with open(self._pending_path(thread_ts), "a", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def load_pending_messages(self, thread_ts: str) -> list[dict]:
        """미관찰 대화 버퍼를 로드합니다. 없으면 빈 리스트."""
        pending_path = self._pending_path(thread_ts)
        if not pending_path.exists():
            return []

        lock = FileLock(str(self._pending_lock_path(thread_ts)), timeout=5)
        with lock:
            messages = []
            with open(pending_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        messages.append(json.loads(line))
            return messages

    def clear_pending_messages(self, thread_ts: str) -> None:
        """관찰 완료 후 미관찰 대화 버퍼를 비웁니다."""
        pending_path = self._pending_path(thread_ts)
        if pending_path.exists():
            lock = FileLock(str(self._pending_lock_path(thread_ts)), timeout=5)
            with lock:
                pending_path.unlink()

    def _new_obs_path(self, thread_ts: str) -> Path:
        return self.observations_dir / f"{thread_ts}.new.md"

    def save_new_observations(self, thread_ts: str, content: str) -> None:
        """이번 턴에서 새로 추가된 관찰만 별도 저장합니다."""
        self._ensure_dirs()
        self._new_obs_path(thread_ts).write_text(content, encoding="utf-8")

    def get_new_observations(self, thread_ts: str) -> str:
        """저장된 새 관찰을 반환합니다. 없으면 빈 문자열."""
        path = self._new_obs_path(thread_ts)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def clear_new_observations(self, thread_ts: str) -> None:
        """주입 완료된 새 관찰을 클리어합니다."""
        path = self._new_obs_path(thread_ts)
        if path.exists():
            path.unlink()

    def _inject_flag_path(self, thread_ts: str) -> Path:
        return self.observations_dir / f"{thread_ts}.inject"

    def set_inject_flag(self, thread_ts: str) -> None:
        """다음 요청에 OM을 주입하도록 플래그를 설정합니다."""
        self._ensure_dirs()
        self._inject_flag_path(thread_ts).write_text("1", encoding="utf-8")

    def check_and_clear_inject_flag(self, thread_ts: str) -> bool:
        """inject 플래그를 확인하고 있으면 제거합니다.

        Returns:
            True: 플래그가 있었음 (주입 필요), False: 없었음
        """
        flag_path = self._inject_flag_path(thread_ts)
        if flag_path.exists():
            flag_path.unlink()
            return True
        return False

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

    # ── candidates (장기 기억 후보) ─────────────────────────────

    def _candidates_path(self, thread_ts: str) -> Path:
        return self.candidates_dir / f"{thread_ts}.jsonl"

    def _candidates_lock_path(self, thread_ts: str) -> Path:
        return self.candidates_dir / f"{thread_ts}.lock"

    def append_candidates(self, thread_ts: str, entries: list[dict]) -> None:
        """후보 항목을 세션별 파일에 누적합니다."""
        self._ensure_dirs()

        lock = FileLock(str(self._candidates_lock_path(thread_ts)), timeout=5)
        with lock:
            with open(self._candidates_path(thread_ts), "a", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_candidates(self, thread_ts: str) -> list[dict]:
        """세션별 후보를 로드합니다. 없으면 빈 리스트."""
        path = self._candidates_path(thread_ts)
        if not path.exists():
            return []

        lock = FileLock(str(self._candidates_lock_path(thread_ts)), timeout=5)
        with lock:
            entries = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            return entries

    def load_all_candidates(self) -> list[dict]:
        """전체 세션의 후보를 수집합니다."""
        if not self.candidates_dir.exists():
            return []

        all_entries = []
        for path in sorted(self.candidates_dir.glob("*.jsonl")):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        all_entries.append(json.loads(line))
        return all_entries

    def count_all_candidate_tokens(self) -> int:
        """전체 후보의 content 필드 토큰 합산."""
        from seosoyoung.memory.token_counter import TokenCounter

        candidates = self.load_all_candidates()
        if not candidates:
            return 0

        counter = TokenCounter()
        total = 0
        for entry in candidates:
            total += counter.count_string(entry.get("content", ""))
        return total

    def clear_all_candidates(self) -> None:
        """모든 후보 파일을 삭제합니다."""
        if not self.candidates_dir.exists():
            return

        for path in self.candidates_dir.glob("*.jsonl"):
            path.unlink()
        for path in self.candidates_dir.glob("*.lock"):
            path.unlink()

    # ── persistent (장기 기억) ──────────────────────────────────

    def _persistent_content_path(self) -> Path:
        return self.persistent_dir / "recent.md"

    def _persistent_meta_path(self) -> Path:
        return self.persistent_dir / "recent.meta.json"

    def _persistent_lock_path(self) -> Path:
        return self.persistent_dir / "recent.lock"

    def _persistent_archive_dir(self) -> Path:
        return self.persistent_dir / "archive"

    def get_persistent(self) -> dict | None:
        """장기 기억을 로드합니다. 없으면 None.

        Returns:
            {"content": str, "meta": dict} 또는 None
        """
        content_path = self._persistent_content_path()
        if not content_path.exists():
            return None

        lock = FileLock(str(self._persistent_lock_path()), timeout=5)
        with lock:
            content = content_path.read_text(encoding="utf-8")
            meta = {}
            meta_path = self._persistent_meta_path()
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return {"content": content, "meta": meta}

    def save_persistent(self, content: str, meta: dict) -> None:
        """장기 기억을 저장합니다."""
        self._ensure_dirs()

        lock = FileLock(str(self._persistent_lock_path()), timeout=5)
        with lock:
            self._persistent_content_path().write_text(content, encoding="utf-8")
            self._persistent_meta_path().write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def archive_persistent(self) -> Path | None:
        """기존 장기 기억을 archive/에 백업합니다.

        Returns:
            아카이브 파일 경로 또는 None (장기 기억이 없을 때)
        """
        content_path = self._persistent_content_path()
        if not content_path.exists():
            return None

        archive_dir = self._persistent_archive_dir()
        archive_dir.mkdir(parents=True, exist_ok=True)

        lock = FileLock(str(self._persistent_lock_path()), timeout=5)
        with lock:
            content = content_path.read_text(encoding="utf-8")
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S%f")
            archive_path = archive_dir / f"recent_{timestamp}.md"
            archive_path.write_text(content, encoding="utf-8")
            return archive_path
