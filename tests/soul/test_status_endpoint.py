"""
test_status_endpoint - /status 엔드포인트 테스트

runner_pool stats가 /status 응답에 포함되는지 검증합니다.
TaskManager와 pool을 mock으로 대체합니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import seosoyoung.soul.main as main_module
from seosoyoung.soul.main import app
from seosoyoung.soul.service.runner_pool import ClaudeRunnerPool


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def make_mock_task_manager():
    tm = MagicMock()
    tm.get_running_tasks.return_value = []
    return tm


def make_mock_pool(stats: dict | None = None):
    pool = MagicMock(spec=ClaudeRunnerPool)
    default_stats = {
        "session_count": 2,
        "generic_count": 1,
        "total": 3,
        "max_size": 5,
        "hits": 42,
        "misses": 8,
        "evictions": 2,
    }
    pool.stats.return_value = stats if stats is not None else default_stats
    return pool


# ─────────────────────────────────────────────
# 테스트
# ─────────────────────────────────────────────


class TestStatusEndpoint:
    def test_status_includes_runner_pool_stats(self):
        """/status 응답에 runner_pool 통계가 포함됨"""
        mock_pool = make_mock_pool()
        mock_task_manager = make_mock_task_manager()

        with (
            patch.object(main_module, "_runner_pool", mock_pool),
            patch(
                "seosoyoung.soul.main.get_task_manager",
                return_value=mock_task_manager,
            ),
        ):
            client = TestClient(app)
            response = client.get("/status")

        assert response.status_code == 200
        data = response.json()

        assert "runner_pool" in data
        pool_stats = data["runner_pool"]
        assert pool_stats["session_count"] == 2
        assert pool_stats["generic_count"] == 1
        assert pool_stats["total"] == 3
        assert pool_stats["max_size"] == 5
        assert pool_stats["hits"] == 42
        assert pool_stats["misses"] == 8
        assert pool_stats["evictions"] == 2

    def test_status_no_runner_pool_stats_when_pool_is_none(self):
        """/status 응답에서 pool=None이면 runner_pool 필드 없음"""
        mock_task_manager = make_mock_task_manager()

        with (
            patch.object(main_module, "_runner_pool", None),
            patch(
                "seosoyoung.soul.main.get_task_manager",
                return_value=mock_task_manager,
            ),
        ):
            client = TestClient(app)
            response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert "runner_pool" not in data

    def test_status_includes_active_tasks(self):
        """/status 응답에 active_tasks 포함"""
        mock_task = MagicMock()
        mock_task.client_id = "client-1"
        mock_task.request_id = "req-1"
        mock_task.status = "running"
        mock_task.created_at.isoformat.return_value = "2026-02-26T00:00:00"

        mock_task_manager = MagicMock()
        mock_task_manager.get_running_tasks.return_value = [mock_task]

        with (
            patch.object(main_module, "_runner_pool", None),
            patch(
                "seosoyoung.soul.main.get_task_manager",
                return_value=mock_task_manager,
            ),
        ):
            client = TestClient(app)
            response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["active_tasks"] == 1
        assert len(data["tasks"]) == 1
        assert data["tasks"][0]["client_id"] == "client-1"

    def test_status_pool_stats_zero_when_empty(self):
        """/status 응답에 빈 풀 통계가 올바르게 반영됨"""
        mock_pool = make_mock_pool(stats={
            "session_count": 0,
            "generic_count": 0,
            "total": 0,
            "max_size": 5,
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        })
        mock_task_manager = make_mock_task_manager()

        with (
            patch.object(main_module, "_runner_pool", mock_pool),
            patch(
                "seosoyoung.soul.main.get_task_manager",
                return_value=mock_task_manager,
            ),
        ):
            client = TestClient(app)
            response = client.get("/status")

        assert response.status_code == 200
        data = response.json()
        pool_stats = data["runner_pool"]
        assert pool_stats["total"] == 0
        assert pool_stats["hits"] == 0
