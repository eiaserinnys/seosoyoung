"""채널 관찰 데이터 저장소

파일 기반으로 채널 단위의 관찰 데이터를 관리합니다.

저장 구조:
    memory/channel/{channel_id}/
    ├── digest.md              # 전체 누적 관찰 요약
    ├── digest.meta.json       # 메타데이터
    ├── buffer_channel.jsonl   # 미소화 채널 루트 메시지
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

    # ── 채널 루트 메시지 버퍼 ────────────────────────────

    def _channel_buffer_path(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "buffer_channel.jsonl"

    def _channel_buffer_lock(self, channel_id: str) -> Path:
        return self._channel_dir(channel_id) / "buffer_channel.lock"

    def append_channel_message(self, channel_id: str, message: dict) -> None:
        """채널 루트 메시지를 버퍼에 추가"""
        self._ensure_channel_dir(channel_id)
        lock = FileLock(str(self._channel_buffer_lock(channel_id)), timeout=5)
        with lock:
            with open(self._channel_buffer_path(channel_id), "a", encoding="utf-8") as f:
                f.write(json.dumps(message, ensure_ascii=False) + "\n")

    def load_channel_buffer(self, channel_id: str) -> list[dict]:
        """채널 루트 메시지 버퍼를 로드. 없으면 빈 리스트."""
        path = self._channel_buffer_path(channel_id)
        if not path.exists():
            return []

        lock = FileLock(str(self._channel_buffer_lock(channel_id)), timeout=5)
        with lock:
            return self._read_jsonl(path)

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

    def count_buffer_tokens(self, channel_id: str) -> int:
        """버퍼 총 토큰 수 (채널 + 스레드 합산)"""
        from seosoyoung.memory.token_counter import TokenCounter

        counter = TokenCounter()
        total = 0

        # 채널 버퍼
        for msg in self.load_channel_buffer(channel_id):
            total += counter.count_string(msg.get("text", ""))

        # 스레드 버퍼
        for thread_msgs in self.load_all_thread_buffers(channel_id).values():
            for msg in thread_msgs:
                total += counter.count_string(msg.get("text", ""))

        return total

    # ── 버퍼 비우기 ──────────────────────────────────────

    def clear_buffers(self, channel_id: str) -> None:
        """소화 완료 후 채널+스레드 버퍼를 비운다."""
        # 채널 버퍼
        channel_buf = self._channel_buffer_path(channel_id)
        if channel_buf.exists():
            channel_buf.unlink()

        # 스레드 버퍼 디렉토리
        threads_dir = self._threads_dir(channel_id)
        if threads_dir.exists():
            for path in threads_dir.glob("*.jsonl"):
                path.unlink()
            for path in threads_dir.glob("*.lock"):
                path.unlink()

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
