"""Git Poll Watcher — eb_narrative/eb_lore HEAD 감시 + 인덱스 자동 재빌드.

백그라운드 스레드에서 git refs를 주기적으로 폴링하여 원격 변경을 감지하고,
변경 시 git pull → 인덱스 재빌드를 수행한다.

핵심 설계:
- swap-on-complete: 재빌드 중에도 기존 인덱스로 검색 서비스 유지
- lock 파일: pre-commit hook(.tools/build-dialogue-index)과 동시 빌드 방지
- 재빌드 실패 시 기존 인덱스 유지 + 에러 로깅
"""

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# 빌드 lock 파일 경로 (pre-commit hook과 공유)
_DEFAULT_LOCK_NAME = "index_build.lock"


class BuildLock:
    """파일 기반 빌드 lock — pre-commit hook과 동시 빌드 방지."""

    def __init__(self, lock_path: Path):
        self._lock_path = lock_path

    def acquire(self, owner: str = "git_watcher", timeout: float = 10.0) -> bool:
        """lock 획득 시도. timeout 내 획득 못 하면 False."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                # 원자적 생성 시도 (exclusive create)
                self._lock_path.parent.mkdir(parents=True, exist_ok=True)
                fd = self._lock_path.open("x", encoding="utf-8")
                fd.write(f"{owner}:{datetime.now(timezone.utc).isoformat()}")
                fd.close()
                return True
            except FileExistsError:
                # 이미 lock이 있음 — stale 체크 (5분 이상이면 stale로 간주)
                try:
                    mtime = self._lock_path.stat().st_mtime
                    if time.time() - mtime > 300:
                        logger.warning("Stale lock detected, removing: %s", self._lock_path)
                        self._lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                time.sleep(0.5)
        return False

    def release(self):
        """lock 해제."""
        self._lock_path.unlink(missing_ok=True)

    @property
    def is_locked(self) -> bool:
        return self._lock_path.exists()


class IndexStatus:
    """인덱스 상태 정보 — lore_index_status 도구에서 조회."""

    def __init__(self):
        self.last_build_time: str | None = None
        self.last_head_narrative: str | None = None
        self.last_head_lore: str | None = None
        self.doc_count_dialogue: int = 0
        self.doc_count_lore: int = 0
        self.is_building: bool = False
        self.last_error: str | None = None
        self.poll_count: int = 0

    def to_dict(self) -> dict:
        return {
            "last_build_time": self.last_build_time,
            "last_head_narrative": self.last_head_narrative,
            "last_head_lore": self.last_head_lore,
            "doc_count_dialogue": self.doc_count_dialogue,
            "doc_count_lore": self.doc_count_lore,
            "is_building": self.is_building,
            "last_error": self.last_error,
            "poll_count": self.poll_count,
        }


def _read_git_head(repo_path: Path) -> str | None:
    """git rev-parse HEAD로 현재 HEAD 해시를 읽는다."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("Failed to read git HEAD at %s: %s", repo_path, e)
    return None


def _git_pull(repo_path: Path) -> bool:
    """git pull을 수행한다. 성공 시 True."""
    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            capture_output=True,
            text=True,
            cwd=str(repo_path),
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("git pull succeeded at %s: %s", repo_path, result.stdout.strip())
            return True
        else:
            logger.error("git pull failed at %s: %s", repo_path, result.stderr.strip())
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.error("git pull error at %s: %s", repo_path, e)
    return False


class GitWatcher:
    """Git HEAD 폴링 워처 — 백그라운드 스레드로 실행.

    Args:
        narrative_path: eb_narrative 리포 경로
        lore_path: eb_lore 리포 경로
        index_root: 인덱스 루트 디렉토리
        poll_interval: 폴링 간격 (초, 기본 60)
        on_rebuild: 재빌드 완료 콜백 (인덱스 핫 리로드용)
    """

    def __init__(
        self,
        narrative_path: Path,
        lore_path: Path,
        index_root: Path,
        poll_interval: float = 60.0,
        on_rebuild: Callable | None = None,
    ):
        self._narrative_path = Path(narrative_path)
        self._lore_path = Path(lore_path)
        self._index_root = Path(index_root)
        self._poll_interval = poll_interval
        self._on_rebuild = on_rebuild

        self._lock = BuildLock(self._index_root / _DEFAULT_LOCK_NAME)
        self.status = IndexStatus()

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # 초기 HEAD 해시
        self._last_narrative_head: str | None = None
        self._last_lore_head: str | None = None

    def start(self):
        """워처 백그라운드 스레드 시작."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("GitWatcher already running")
            return

        self._stop_event.clear()

        # 초기 HEAD 기록 (첫 poll에서 불필요한 재빌드 방지)
        self._last_narrative_head = _read_git_head(self._narrative_path)
        self._last_lore_head = _read_git_head(self._lore_path)
        self.status.last_head_narrative = self._last_narrative_head
        self.status.last_head_lore = self._last_lore_head

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="git-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "GitWatcher started (interval=%ss, narrative=%s, lore=%s)",
            self._poll_interval,
            self._narrative_path,
            self._lore_path,
        )

    def stop(self, timeout: float = 5.0):
        """워처 정지."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("GitWatcher stopped")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _poll_loop(self):
        """메인 폴링 루프."""
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception as e:
                logger.error("GitWatcher poll error: %s", e, exc_info=True)
                self.status.last_error = str(e)

            # 인터럽트 가능한 대기
            self._stop_event.wait(timeout=self._poll_interval)

    def _poll_once(self):
        """한 번의 폴링 사이클."""
        self.status.poll_count += 1

        narrative_head = _read_git_head(self._narrative_path)
        lore_head = _read_git_head(self._lore_path)

        changed_repos: list[Path] = []

        if narrative_head and narrative_head != self._last_narrative_head:
            logger.info(
                "eb_narrative HEAD changed: %s → %s",
                self._last_narrative_head,
                narrative_head,
            )
            changed_repos.append(self._narrative_path)

        if lore_head and lore_head != self._last_lore_head:
            logger.info(
                "eb_lore HEAD changed: %s → %s",
                self._last_lore_head,
                lore_head,
            )
            changed_repos.append(self._lore_path)

        if not changed_repos:
            return

        # git pull
        for repo in changed_repos:
            _git_pull(repo)

        # HEAD 갱신 (pull 후)
        new_narrative_head = _read_git_head(self._narrative_path)
        new_lore_head = _read_git_head(self._lore_path)

        # 인덱스 재빌드
        self._rebuild_index()

        # 상태 갱신
        self._last_narrative_head = new_narrative_head
        self._last_lore_head = new_lore_head
        self.status.last_head_narrative = new_narrative_head
        self.status.last_head_lore = new_lore_head

    def _rebuild_index(self):
        """인덱스 재빌드 (swap-on-complete 전략)."""
        if not self._lock.acquire(owner="git_watcher", timeout=30.0):
            logger.warning("Could not acquire build lock, skipping rebuild")
            self.status.last_error = "Build lock timeout"
            return

        self.status.is_building = True

        try:
            from .build import build_whoosh

            # swap-on-complete: 임시 디렉토리에 빌드 후 교체
            tmp_root = self._index_root / "_rebuild_tmp"
            tmp_root.mkdir(parents=True, exist_ok=True)

            stats = build_whoosh(
                narrative_path=self._narrative_path,
                lore_path=self._lore_path,
                index_root=tmp_root,
                force=True,
            )

            # 성공 시 기존 인덱스와 교체
            self._swap_indices(tmp_root)

            self.status.last_build_time = datetime.now(timezone.utc).isoformat()
            self.status.doc_count_dialogue = stats.get("dialogue", {}).get("dialogues", 0)
            self.status.doc_count_lore = stats.get("lore", {}).get("chunks", 0)
            self.status.last_error = None

            logger.info("Index rebuild completed: %s", stats)

            # 콜백으로 인메모리 인덱스 핫 리로드 알림
            if self._on_rebuild:
                try:
                    self._on_rebuild()
                except Exception as e:
                    logger.error("on_rebuild callback error: %s", e)

        except Exception as e:
            logger.error("Index rebuild failed: %s", e, exc_info=True)
            self.status.last_error = str(e)
            # 실패 시 기존 인덱스 유지 — 임시 디렉토리만 정리
            self._cleanup_tmp()
        finally:
            self.status.is_building = False
            self._lock.release()

    def _swap_indices(self, tmp_root: Path):
        """임시 빌드 결과물을 실제 인덱스 위치로 교체.

        Whoosh 인덱스는 디렉토리 단위이므로,
        기존 디렉토리를 백업 → 새 디렉토리를 이동 → 백업 삭제.
        """
        import shutil

        for subdir in ("dialogues", "lore"):
            src = tmp_root / subdir
            dst = self._index_root / subdir
            bak = self._index_root / f"{subdir}_bak"

            if not src.exists():
                continue

            # 기존 → 백업
            if dst.exists():
                if bak.exists():
                    shutil.rmtree(bak)
                dst.rename(bak)

            # 새 → 실제 위치
            src.rename(dst)

            # 백업 삭제
            if bak.exists():
                shutil.rmtree(bak)

        # 임시 루트 정리
        if tmp_root.exists():
            shutil.rmtree(tmp_root)

    def _cleanup_tmp(self):
        """재빌드 실패 시 임시 디렉토리 정리."""
        import shutil

        tmp_root = self._index_root / "_rebuild_tmp"
        if tmp_root.exists():
            shutil.rmtree(tmp_root, ignore_errors=True)
