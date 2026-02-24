"""GitWatcher 테스트.

git_watcher.py의 핵심 기능을 검증:
1. BuildLock — 파일 기반 lock 획득/해제, stale 처리
2. IndexStatus — 상태 조회 dict 직렬화
3. GitWatcher — HEAD 변경 감지, 재빌드 트리거, swap-on-complete
4. _read_git_head / _git_pull — 유틸리티 함수
"""

import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from seosoyoung.slackbot.search.git_watcher import (
    BuildLock,
    IndexStatus,
    GitWatcher,
    _read_git_head,
    _git_pull,
)


# ============================================================================
# BuildLock 테스트
# ============================================================================


class TestBuildLock:
    def test_acquire_release(self, tmp_path):
        """lock 획득 후 해제."""
        lock = BuildLock(tmp_path / "test.lock")
        assert lock.acquire(owner="test")
        assert lock.is_locked
        lock.release()
        assert not lock.is_locked

    def test_acquire_fails_when_locked(self, tmp_path):
        """이미 lock이 있으면 timeout 후 False."""
        lock_path = tmp_path / "test.lock"
        lock_path.write_text("other:locked")

        lock = BuildLock(lock_path)
        result = lock.acquire(timeout=0.5)
        assert result is False

    def test_stale_lock_removed(self, tmp_path):
        """5분 이상 된 lock은 stale로 간주하여 제거."""
        lock_path = tmp_path / "test.lock"
        lock_path.write_text("stale:locked")
        # mtime을 10분 전으로 설정
        import os

        old_time = time.time() - 600
        os.utime(lock_path, (old_time, old_time))

        lock = BuildLock(lock_path)
        result = lock.acquire(timeout=2.0)
        assert result is True
        lock.release()

    def test_release_nonexistent(self, tmp_path):
        """존재하지 않는 lock 해제 시 에러 없음."""
        lock = BuildLock(tmp_path / "nonexistent.lock")
        lock.release()  # should not raise

    def test_concurrent_acquire(self, tmp_path):
        """두 lock이 동시에 경합하면 하나만 성공."""
        lock_path = tmp_path / "concurrent.lock"
        lock1 = BuildLock(lock_path)
        lock2 = BuildLock(lock_path)

        results = []

        def try_acquire(lock, name):
            r = lock.acquire(timeout=1.0)
            results.append((name, r))

        t1 = threading.Thread(target=try_acquire, args=(lock1, "lock1"))
        t2 = threading.Thread(target=try_acquire, args=(lock2, "lock2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        acquired = [name for name, r in results if r]
        assert len(acquired) == 1  # 하나만 성공

        lock1.release()
        lock2.release()


# ============================================================================
# IndexStatus 테스트
# ============================================================================


class TestIndexStatus:
    def test_initial_state(self):
        """초기 상태 확인."""
        status = IndexStatus()
        d = status.to_dict()
        assert d["last_build_time"] is None
        assert d["is_building"] is False
        assert d["poll_count"] == 0

    def test_to_dict_after_update(self):
        """상태 업데이트 후 dict 변환."""
        status = IndexStatus()
        status.last_build_time = "2025-01-01T00:00:00Z"
        status.doc_count_dialogue = 100
        status.poll_count = 5

        d = status.to_dict()
        assert d["last_build_time"] == "2025-01-01T00:00:00Z"
        assert d["doc_count_dialogue"] == 100
        assert d["poll_count"] == 5


# ============================================================================
# _read_git_head / _git_pull 테스트
# ============================================================================


class TestGitUtils:
    @patch("seosoyoung.slackbot.search.git_watcher.subprocess.run")
    def test_read_git_head_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc123def456\n"
        )
        head = _read_git_head(Path("/fake/repo"))
        assert head == "abc123def456"

    @patch("seosoyoung.slackbot.search.git_watcher.subprocess.run")
    def test_read_git_head_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error"
        )
        head = _read_git_head(Path("/fake/repo"))
        assert head is None

    @patch("seosoyoung.slackbot.search.git_watcher.subprocess.run")
    def test_read_git_head_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        head = _read_git_head(Path("/fake/repo"))
        assert head is None

    @patch("seosoyoung.slackbot.search.git_watcher.subprocess.run")
    def test_git_pull_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Already up to date.\n"
        )
        assert _git_pull(Path("/fake/repo")) is True

    @patch("seosoyoung.slackbot.search.git_watcher.subprocess.run")
    def test_git_pull_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="merge conflict"
        )
        assert _git_pull(Path("/fake/repo")) is False


# ============================================================================
# GitWatcher 테스트
# ============================================================================


class TestGitWatcher:
    @pytest.fixture
    def watcher_env(self, tmp_path):
        """워처 테스트용 환경 구성."""
        narrative = tmp_path / "eb_narrative"
        lore = tmp_path / "eb_lore"
        index_root = tmp_path / "index"
        narrative.mkdir()
        lore.mkdir()
        index_root.mkdir()
        return {
            "narrative_path": narrative,
            "lore_path": lore,
            "index_root": index_root,
        }

    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_start_stop(self, mock_head, watcher_env):
        """워처 시작/종료가 정상 동작."""
        mock_head.return_value = "abc123"

        watcher = GitWatcher(
            poll_interval=0.1,
            **watcher_env,
        )

        watcher.start()
        assert watcher.is_running

        watcher.stop(timeout=2.0)
        assert not watcher.is_running

    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_initial_head_stored(self, mock_head, watcher_env):
        """시작 시 초기 HEAD가 저장됨."""
        mock_head.side_effect = ["narrative_head", "lore_head"]

        watcher = GitWatcher(poll_interval=60, **watcher_env)
        watcher.start()

        assert watcher.status.last_head_narrative == "narrative_head"
        assert watcher.status.last_head_lore == "lore_head"

        watcher.stop()

    @patch("seosoyoung.slackbot.search.git_watcher._git_pull")
    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_no_rebuild_when_unchanged(self, mock_head, mock_pull, watcher_env):
        """HEAD 변경 없으면 rebuild/pull 호출 안 함."""
        mock_head.return_value = "same_head"

        watcher = GitWatcher(poll_interval=0.1, **watcher_env)
        watcher.start()
        time.sleep(0.5)
        watcher.stop()

        mock_pull.assert_not_called()

    @patch("seosoyoung.slackbot.search.git_watcher.GitWatcher._rebuild_index")
    @patch("seosoyoung.slackbot.search.git_watcher._git_pull")
    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_rebuild_on_narrative_change(
        self, mock_head, mock_pull, mock_rebuild, watcher_env
    ):
        """eb_narrative HEAD 변경 시 git pull + rebuild 호출."""
        call_count = 0

        def head_side_effect(repo_path):
            nonlocal call_count
            call_count += 1
            # 초기: start()에서 2회 호출 (narrative, lore)
            # poll: 짝수=narrative, 홀수=lore
            if call_count <= 2:
                return "initial"
            # poll 사이클에서 narrative HEAD 변경
            repo_str = str(repo_path)
            if "narrative" in repo_str:
                return "changed_head"
            return "initial"

        mock_head.side_effect = head_side_effect
        mock_pull.return_value = True

        watcher = GitWatcher(poll_interval=0.1, **watcher_env)
        watcher.start()
        time.sleep(0.8)
        watcher.stop()

        mock_pull.assert_called()
        mock_rebuild.assert_called()

    @patch("seosoyoung.slackbot.search.git_watcher.GitWatcher._rebuild_index")
    @patch("seosoyoung.slackbot.search.git_watcher._git_pull")
    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_rebuild_on_lore_change(
        self, mock_head, mock_pull, mock_rebuild, watcher_env
    ):
        """eb_lore HEAD 변경 시 git pull + rebuild 호출."""
        call_count = 0

        def head_side_effect(repo_path):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return "initial"
            repo_str = str(repo_path)
            if "lore" in repo_str:
                return "changed_head"
            return "initial"

        mock_head.side_effect = head_side_effect
        mock_pull.return_value = True

        watcher = GitWatcher(poll_interval=0.1, **watcher_env)
        watcher.start()
        time.sleep(0.8)
        watcher.stop()

        mock_pull.assert_called()
        mock_rebuild.assert_called()

    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_on_rebuild_callback(self, mock_head, watcher_env):
        """재빌드 완료 시 on_rebuild 콜백 호출."""
        callback = MagicMock()

        # _rebuild_index를 직접 호출하되, build_whoosh를 모킹
        with patch("seosoyoung.slackbot.search.git_watcher.BuildLock.acquire", return_value=True), \
             patch("seosoyoung.slackbot.search.git_watcher.BuildLock.release"), \
             patch("seosoyoung.slackbot.search.build.build_whoosh", return_value={
                 "dialogue": {"dialogues": 50},
                 "lore": {"chunks": 10},
             }), \
             patch.object(GitWatcher, "_swap_indices"):

            mock_head.return_value = "abc123"

            watcher = GitWatcher(
                on_rebuild=callback,
                poll_interval=60,
                **watcher_env,
            )
            watcher._rebuild_index()

            callback.assert_called_once()
            assert watcher.status.last_build_time is not None
            assert watcher.status.last_error is None

    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_rebuild_failure_keeps_existing(self, mock_head, watcher_env):
        """재빌드 실패 시 기존 인덱스 유지, 에러 로깅."""
        with patch("seosoyoung.slackbot.search.git_watcher.BuildLock.acquire", return_value=True), \
             patch("seosoyoung.slackbot.search.git_watcher.BuildLock.release"), \
             patch("seosoyoung.slackbot.search.build.build_whoosh", side_effect=RuntimeError("build error")), \
             patch.object(GitWatcher, "_cleanup_tmp"):

            mock_head.return_value = "abc123"

            watcher = GitWatcher(poll_interval=60, **watcher_env)
            watcher._rebuild_index()

            assert watcher.status.last_error == "build error"
            assert watcher.status.is_building is False

    @patch("seosoyoung.slackbot.search.git_watcher._read_git_head")
    def test_rebuild_skipped_when_lock_unavailable(self, mock_head, watcher_env):
        """lock을 획득하지 못하면 rebuild를 건너뜀."""
        with patch("seosoyoung.slackbot.search.git_watcher.BuildLock.acquire", return_value=False):
            mock_head.return_value = "abc123"

            watcher = GitWatcher(poll_interval=60, **watcher_env)
            watcher._rebuild_index()

            assert watcher.status.last_error == "Build lock timeout"


class TestSwapIndices:
    """swap-on-complete 테스트."""

    def test_swap_creates_new_index(self, tmp_path):
        """임시 빌드 결과물이 실제 위치로 교체됨."""
        index_root = tmp_path / "index"
        index_root.mkdir()

        tmp_root = index_root / "_rebuild_tmp"
        tmp_dialogues = tmp_root / "dialogues"
        tmp_dialogues.mkdir(parents=True)
        (tmp_dialogues / "MAIN_abc.seg").write_text("new index")

        with patch("seosoyoung.slackbot.search.git_watcher._read_git_head", return_value="abc"):
            watcher = GitWatcher(
                narrative_path=tmp_path / "n",
                lore_path=tmp_path / "l",
                index_root=index_root,
            )
            watcher._swap_indices(tmp_root)

        # 새 인덱스가 실제 위치에 있는지
        assert (index_root / "dialogues" / "MAIN_abc.seg").exists()
        # 임시 디렉토리 정리됨
        assert not tmp_root.exists()

    def test_swap_replaces_existing(self, tmp_path):
        """기존 인덱스가 있으면 교체."""
        index_root = tmp_path / "index"
        old_dialogues = index_root / "dialogues"
        old_dialogues.mkdir(parents=True)
        (old_dialogues / "MAIN_old.seg").write_text("old index")

        tmp_root = index_root / "_rebuild_tmp"
        new_dialogues = tmp_root / "dialogues"
        new_dialogues.mkdir(parents=True)
        (new_dialogues / "MAIN_new.seg").write_text("new index")

        with patch("seosoyoung.slackbot.search.git_watcher._read_git_head", return_value="abc"):
            watcher = GitWatcher(
                narrative_path=tmp_path / "n",
                lore_path=tmp_path / "l",
                index_root=index_root,
            )
            watcher._swap_indices(tmp_root)

        # 새 파일 존재, 옛 파일 없음
        assert (index_root / "dialogues" / "MAIN_new.seg").exists()
        assert not (index_root / "dialogues" / "MAIN_old.seg").exists()
        # 백업도 정리됨
        assert not (index_root / "dialogues_bak").exists()
