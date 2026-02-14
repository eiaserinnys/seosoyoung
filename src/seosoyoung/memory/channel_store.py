"""채널 관찰 데이터 저장소

파일 기반으로 채널 단위의 관찰 데이터를 관리합니다.

저장 구조:
    memory/channel/{channel_id}/
    ├── digest.md              # 전체 누적 관찰 요약
    ├── digest.meta.json       # 메타데이터
    ├── pending.jsonl          # 아직 LLM이 보지 않은 새 대화
    ├── judged.jsonl           # LLM이 이미 리액션 판단을 거친 대화
    └── buffer_threads/
        └── {thread_ts}.jsonl  # 미소화 스레드별 메시지
"""

import json
import logging
from pathlib import Path

from filelock import FileLock

logger = logging.getLogger(__name__)


class ChannelStore:
    """파일 기반 채널 관찰 데이터 저장소

    channel_id를 기본 키로 사용합니다.
    """

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def _channel_dir(self, channel_id: str) -> Path:
        return self.base_dir / "channel" / channel_id

    def _ensure_channel_dir(self, channel_id: str) -> Path:
        d = self._channel_dir(channel_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _threads_dir(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "buffer_threads"

    def _ensure_threads_dir(self, channel_id: str) -> Path:
        d = self._threads_dir(channel_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── pending 버퍼 (아직 LLM이 보지 않은 새 대화) ────────

    def _pending_path(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "pending.jsonl"

    def _pending_lock(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "pending.lock"

    def append_pending(self, channel_id: str, message: dict) -> None:
        """채널 루트 메시지를 pending 버퍼에 추가"""
        self._ensure_channel_dir(channel_id)
        lock = FileLock(str(self._pending_lock(channel_id)), timeout=5)
        with lock:
            with open(self._pending_path(channel_id), "a", encoding="utf-8") as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def load_pending(self, channel_id: str) -> list[dict]:
        """pending 버퍼를 로드. 없으면 빈 리스트."""
        path = self._pending_path(channel_id)
        if not path.exists():
            return []

        lock = FileLock(str(self._pending_lock(channel_id)), timeout=5)
        with lock:
            return self._read_jsonl(path)

    def clear_pending(self, channel_id: str) -> None:
        """pending 버퍼만 비운다."""
        path = self._pending_path(channel_id)
        if path.exists():
            path.unlink()

    # ── 하위호환 별칭 ──────────────────────────────────────

    def append_channel_message(self, channel_id: str, message: dict) -> None:
        """append_pending의 하위호환 별칭"""
        return self.append_pending(channel_id, message)

    def load_channel_buffer(self, channel_id: str) -> list[dict]:
        """load_pending의 하위호환 별칭"""
        return self.load_pending(channel_id)

    # ── judged 버퍼 (LLM이 이미 판단을 거친 대화) ──────────

    def _judged_path(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "judged.jsonl"

    def _judged_lock(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "judged.lock"

    def append_judged(self, channel_id: str, messages: list[dict]) -> None:
        """judged 버퍼에 메시지들을 추가"""
        self._ensure_channel_dir(channel_id)
        lock = FileLock(str(self._judged_lock(channel_id)), timeout=5)
        with lock:
            with open(self._judged_path(channel_id), "a", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def load_judged(self, channel_id: str) -> list[dict]:
        """judged 버퍼를 로드. 없으면 빈 리스트."""
        path = self._judged_path(channel_id)
        if not path.exists():
            return []

        lock = FileLock(str(self._judged_lock(channel_id)), timeout=5)
        with lock:
            return self._read_jsonl(path)

    def clear_judged(self, channel_id: str) -> None:
        """judged 버퍼만 비운다."""
        path = self._judged_path(channel_id)
        if path.exists():
            path.unlink()

    # ── pending → judged 이동 ──────────────────────────────

    def move_pending_to_judged(self, channel_id: str) -> None:
        """pending + 스레드 버퍼를 judged에 append 후 클리어"""
        # 채널 pending → judged
        pending = self.load_pending(channel_id)
        if pending:
            self.append_judged(channel_id, pending)
        self.clear_pending(channel_id)

        # 스레드 버퍼 → judged 후 비우기
        thread_buffers = self.load_all_thread_buffers(channel_id)
        for thread_msgs in thread_buffers.values():
            if thread_msgs:
                self.append_judged(channel_id, thread_msgs)
        self._clear_thread_buffers(channel_id)

    # ── 스레드 메시지 버퍼 ───────────────────────────────

    def _thread_buffer_path(self, channel_id: str, thread_ts: str) -> Path:
        return self._threads_dir(channel_id) / f"{thread_ts}.jsonl"

    def _thread_buffer_lock(self, channel_id: str, thread_ts: str) -> Path:
        return self._threads_dir(channel_id) / f"{thread_ts}.lock"

    def append_thread_message(self, channel_id: str, thread_ts: str, message: dict) -> None:
        """스레드 메시지를 버퍼에 추가"""
        self._ensure_threads_dir(channel_id)
        lock = FileLock(str(self._thread_buffer_lock(channel_id, thread_ts)), timeout=5)
        with lock:
            with open(self._thread_buffer_path(channel_id, thread_ts), "a", encoding="utf-8") as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def load_thread_buffer(self, channel_id: str, thread_ts: str) -> list[dict]:
        """스레드 메시지 버퍼를 로드. 없으면 빈 리스트."""
        path = self._thread_buffer_path(channel_id, thread_ts)
        if not path.exists():
            return []

        lock = FileLock(str(self._thread_buffer_lock(channel_id, thread_ts)), timeout=5)
        with lock:
            return self._read_jsonl(path)

    def load_all_thread_buffers(self, channel_id: str) -> dict[str, list[dict]]:
        """채널의 전체 스레드 버퍼를 로드. {thread_ts: [messages]} 형태."""
        threads_dir = self._threads_dir(channel_id)
        if not threads_dir.exists():
            return {}

        result = {}
        for path in sorted(threads_dir.glob("*.jsonl")):
            thread_ts = path.stem
            messages = self._read_jsonl(path)
            if messages:
                result[thread_ts] = messages
        return result

    # ── 토큰 카운팅 ─────────────────────────────────────

    def _count_messages_tokens(self, messages: list[dict]) -> int:
        """메시지 리스트의 총 토큰 수를 계산"""
        from seosoyoung.memory.token_counter import TokenCounter

        counter = TokenCounter()
        total = 0
        for msg in messages:
            total += counter.count_string(msg.get("text", ""))
        return total

    def count_pending_tokens(self, channel_id: str) -> int:
        """pending 버퍼 총 토큰 수 (채널 + 스레드 합산)"""
        total = self._count_messages_tokens(self.load_pending(channel_id))

        for thread_msgs in self.load_all_thread_buffers(channel_id).values():
            total += self._count_messages_tokens(thread_msgs)

        return total

    def count_judged_plus_pending_tokens(self, channel_id: str) -> int:
        """judged + pending 합산 토큰 수"""
        judged_tokens = self._count_messages_tokens(self.load_judged(channel_id))
        pending_tokens = self.count_pending_tokens(channel_id)
        return judged_tokens + pending_tokens

    def count_buffer_tokens(self, channel_id: str) -> int:
        """count_pending_tokens의 하위호환 별칭"""
        return self.count_pending_tokens(channel_id)

    # ── 버퍼 비우기 ──────────────────────────────────────

    def _clear_thread_buffers(self, channel_id: str) -> None:
        """스레드 버퍼 전체를 비운다."""
        threads_dir = self._threads_dir(channel_id)
        if threads_dir.exists():
            for path in threads_dir.glob("*.jsonl"):
                path.unlink()
            for path in threads_dir.glob("*.lock"):
                path.unlink()

    def clear_buffers(self, channel_id: str) -> None:
        """pending + judged + 스레드 버퍼를 모두 비운다."""
        self.clear_pending(channel_id)
        self.clear_judged(channel_id)
        self._clear_thread_buffers(channel_id)

    # ── digest (관찰 요약) ───────────────────────────────

    def _digest_path(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "digest.md"

    def _digest_meta_path(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "digest.meta.json"

    def _digest_lock_path(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "digest.lock"

    def get_digest(self, channel_id: str) -> dict | None:
        """digest.md를 로드. 없으면 None.

        Returns:
            {"content": str, "meta": dict} 또는 None
        """
        digest_path = self._digest_path(channel_id)
        if not digest_path.exists():
            return None

        lock = FileLock(str(self._digest_lock_path(channel_id)), timeout=5)
        with lock:
            content = digest_path.read_text(encoding="utf-8")
            meta = {}
            meta_path = self._digest_meta_path(channel_id)
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return {"content": content, "meta": meta}

    def save_digest(self, channel_id: str, content: str, meta: dict) -> None:
        """digest.md를 저장"""
        self._ensure_channel_dir(channel_id)
        lock = FileLock(str(self._digest_lock_path(channel_id)), timeout=5)
        with lock:
            self._digest_path(channel_id).write_text(content, encoding="utf-8")
            self._digest_meta_path(channel_id).write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    # ── reactions 갱신 ───────────────────────────────────

    def update_reactions(
        self, channel_id: str, *, ts: str, emoji: str, user: str, action: str,
    ) -> None:
        """pending/judged/thread 버퍼에서 ts가 일치하는 메시지의 reactions를 갱신합니다.

        Args:
            channel_id: 채널 ID
            ts: 대상 메시지 타임스탬프
            emoji: 이모지 이름 (콜론 없이)
            user: 리액션을 추가/제거한 유저 ID
            action: "added" | "removed"
        """
        updated = self._update_reactions_in_jsonl(
            self._pending_path(channel_id),
            self._pending_lock(channel_id),
            ts, emoji, user, action,
        )
        if updated:
            return

        updated = self._update_reactions_in_jsonl(
            self._judged_path(channel_id),
            self._judged_lock(channel_id),
            ts, emoji, user, action,
        )
        if updated:
            return

        # 스레드 버퍼 순회
        threads_dir = self._threads_dir(channel_id)
        if threads_dir.exists():
            for path in threads_dir.glob("*.jsonl"):
                thread_ts = path.stem
                lock_path = self._thread_buffer_lock(channel_id, thread_ts)
                updated = self._update_reactions_in_jsonl(
                    path, lock_path, ts, emoji, user, action,
                )
                if updated:
                    return

    def _update_reactions_in_jsonl(
        self, path: Path, lock_path: Path,
        ts: str, emoji: str, user: str, action: str,
    ) -> bool:
        """JSONL 파일 내에서 ts가 일치하는 메시지의 reactions를 갱신합니다.

        Returns:
            True if a matching message was found and updated, False otherwise.
        """
        if not path.exists():
            return False

        lock = FileLock(str(lock_path), timeout=5)
        with lock:
            messages = self._read_jsonl(path)
            found = False
            for msg in messages:
                if msg.get("ts") != ts:
                    continue
                found = True
                reactions = msg.setdefault("reactions", [])
                # 해당 이모지 항목 찾기
                entry = None
                for r in reactions:
                    if r["name"] == emoji:
                        entry = r
                        break

                if action == "added":
                    if entry is None:
                        reactions.append({"name": emoji, "users": [user], "count": 1})
                    else:
                        if user not in entry["users"]:
                            entry["users"].append(user)
                            entry["count"] = len(entry["users"])
                elif action == "removed":
                    if entry is not None and user in entry["users"]:
                        entry["users"].remove(user)
                        entry["count"] = len(entry["users"])
                        if entry["count"] == 0:
                            reactions.remove(entry)

                break  # ts는 유니크하므로 첫 매칭만 처리

            if found:
                with open(path, "w", encoding="utf-8") as f:
                    for msg in messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            return found

    # ── 유틸리티 ─────────────────────────────────────────

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        """JSONL 파일을 읽어 리스트로 반환"""
        messages = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    messages.append(json.loads(line))
        return messages
