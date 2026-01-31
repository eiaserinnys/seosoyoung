"""ListRunner 테스트 - 리스트 정주행 기능"""

import json
import pytest
from pathlib import Path
import tempfile


class TestListRunSession:
    """ListRunSession 데이터 클래스 테스트"""

    def test_create_session(self):
        """세션 생성"""
        from seosoyoung.trello.list_runner import ListRunSession, SessionStatus

        session = ListRunSession(
            session_id="session_001",
            list_id="list_abc123",
            list_name="📦 Backlog",
            card_ids=["card1", "card2", "card3"],
            status=SessionStatus.PENDING,
            created_at="2026-01-31T12:00:00",
        )

        assert session.session_id == "session_001"
        assert session.list_id == "list_abc123"
        assert session.list_name == "📦 Backlog"
        assert session.card_ids == ["card1", "card2", "card3"]
        assert session.status == SessionStatus.PENDING
        assert session.current_index == 0
        assert session.verify_session_id is None

    def test_session_status_values(self):
        """세션 상태 값"""
        from seosoyoung.trello.list_runner import SessionStatus

        assert SessionStatus.PENDING.value == "pending"
        assert SessionStatus.RUNNING.value == "running"
        assert SessionStatus.PAUSED.value == "paused"
        assert SessionStatus.VERIFYING.value == "verifying"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.FAILED.value == "failed"

    def test_session_to_dict(self):
        """세션 딕셔너리 변환"""
        from seosoyoung.trello.list_runner import ListRunSession, SessionStatus

        session = ListRunSession(
            session_id="session_001",
            list_id="list_abc123",
            list_name="📦 Backlog",
            card_ids=["card1", "card2"],
            status=SessionStatus.RUNNING,
            created_at="2026-01-31T12:00:00",
            current_index=1,
        )

        data = session.to_dict()

        assert data["session_id"] == "session_001"
        assert data["list_id"] == "list_abc123"
        assert data["status"] == "running"
        assert data["current_index"] == 1

    def test_session_from_dict(self):
        """딕셔너리에서 세션 생성"""
        from seosoyoung.trello.list_runner import ListRunSession, SessionStatus

        data = {
            "session_id": "session_002",
            "list_id": "list_xyz789",
            "list_name": "🔨 In Progress",
            "card_ids": ["cardA", "cardB"],
            "status": "paused",
            "created_at": "2026-01-31T14:00:00",
            "current_index": 0,
            "verify_session_id": "verify_001",
            "processed_cards": {"cardA": "completed"},
            "error_message": None,
        }

        session = ListRunSession.from_dict(data)

        assert session.session_id == "session_002"
        assert session.status == SessionStatus.PAUSED
        assert session.verify_session_id == "verify_001"
        assert session.processed_cards == {"cardA": "completed"}


class TestListRunner:
    """ListRunner 클래스 테스트"""

    def test_create_list_runner(self):
        """ListRunner 생성"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            assert runner.sessions == {}
            assert runner.sessions_file.exists() is False

    def test_create_session(self):
        """새 세션 생성"""
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            session = runner.create_session(
                list_id="list_abc123",
                list_name="📦 Backlog",
                card_ids=["card1", "card2", "card3"],
            )

            assert session.list_id == "list_abc123"
            assert session.list_name == "📦 Backlog"
            assert session.card_ids == ["card1", "card2", "card3"]
            assert session.status == SessionStatus.PENDING
            assert session.session_id in runner.sessions

    def test_get_session(self):
        """세션 조회"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            session = runner.create_session(
                list_id="list_abc123",
                list_name="📦 Backlog",
                card_ids=["card1"],
            )

            retrieved = runner.get_session(session.session_id)
            assert retrieved is not None
            assert retrieved.session_id == session.session_id

    def test_get_session_not_found(self):
        """존재하지 않는 세션 조회"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            retrieved = runner.get_session("nonexistent")
            assert retrieved is None

    def test_save_and_load_sessions(self):
        """세션 저장 및 로드"""
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            # 세션 생성 및 저장
            runner1 = ListRunner(data_dir=Path(tmpdir))
            session = runner1.create_session(
                list_id="list_abc123",
                list_name="📦 Backlog",
                card_ids=["card1", "card2"],
            )
            session.status = SessionStatus.RUNNING
            session.current_index = 1
            runner1.save_sessions()

            # 새 인스턴스에서 로드
            runner2 = ListRunner(data_dir=Path(tmpdir))

            assert session.session_id in runner2.sessions
            loaded = runner2.get_session(session.session_id)
            assert loaded.status == SessionStatus.RUNNING
            assert loaded.current_index == 1

    def test_update_session_status(self):
        """세션 상태 업데이트"""
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_abc123",
                list_name="📦 Backlog",
                card_ids=["card1"],
            )

            runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            assert runner.get_session(session.session_id).status == SessionStatus.RUNNING

    def test_get_active_sessions(self):
        """활성 세션 목록 조회"""
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            # 여러 세션 생성
            s1 = runner.create_session("list1", "List 1", ["card1"])
            s2 = runner.create_session("list2", "List 2", ["card2"])
            s3 = runner.create_session("list3", "List 3", ["card3"])

            # 상태 변경
            runner.update_session_status(s1.session_id, SessionStatus.RUNNING)
            runner.update_session_status(s2.session_id, SessionStatus.COMPLETED)
            runner.update_session_status(s3.session_id, SessionStatus.PAUSED)

            active = runner.get_active_sessions()

            # RUNNING, PAUSED는 활성 세션
            assert len(active) == 2
            session_ids = [s.session_id for s in active]
            assert s1.session_id in session_ids
            assert s3.session_id in session_ids

    def test_mark_card_processed(self):
        """카드 처리 완료 표시"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_abc123",
                list_name="📦 Backlog",
                card_ids=["card1", "card2"],
            )

            runner.mark_card_processed(
                session.session_id,
                card_id="card1",
                result="completed"
            )

            updated = runner.get_session(session.session_id)
            assert updated.processed_cards["card1"] == "completed"
            assert updated.current_index == 1

    def test_get_next_card_id(self):
        """다음 카드 ID 조회"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_abc123",
                list_name="📦 Backlog",
                card_ids=["card1", "card2", "card3"],
            )

            # 첫 번째 카드
            assert runner.get_next_card_id(session.session_id) == "card1"

            # 첫 번째 처리 후
            runner.mark_card_processed(session.session_id, "card1", "completed")
            assert runner.get_next_card_id(session.session_id) == "card2"

            # 모두 처리 후
            runner.mark_card_processed(session.session_id, "card2", "completed")
            runner.mark_card_processed(session.session_id, "card3", "completed")
            assert runner.get_next_card_id(session.session_id) is None


class TestListRunnerPersistence:
    """ListRunner 영속성 테스트"""

    def test_sessions_file_created_on_save(self):
        """저장 시 파일 생성"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            runner.create_session("list1", "List 1", ["card1"])
            runner.save_sessions()

            sessions_file = Path(tmpdir) / "list_run_sessions.json"
            assert sessions_file.exists()

    def test_sessions_file_content(self):
        """저장된 파일 내용 검증"""
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session("list1", "List 1", ["card1", "card2"])
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)
            runner.save_sessions()

            sessions_file = Path(tmpdir) / "list_run_sessions.json"
            with open(sessions_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            assert session.session_id in data
            assert data[session.session_id]["status"] == "running"
            assert data[session.session_id]["card_ids"] == ["card1", "card2"]

    def test_load_from_corrupted_file(self):
        """손상된 파일에서 로드 (빈 상태로 시작)"""
        from seosoyoung.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_file = Path(tmpdir) / "list_run_sessions.json"
            sessions_file.write_text("corrupted json content", encoding="utf-8")

            # 손상된 파일이 있어도 빈 상태로 시작해야 함
            runner = ListRunner(data_dir=Path(tmpdir))
            assert runner.sessions == {}


class TestStartRunByName:
    """start_run_by_name() 메서드 테스트"""

    def test_start_run_by_name_found(self):
        """리스트 이름으로 정주행 시작 - 성공"""
        from seosoyoung.trello.list_runner import ListRunner, SessionStatus
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            # Mock trello client
            mock_trello = MagicMock()
            mock_trello.get_lists = AsyncMock(return_value=[
                {"id": "list_123", "name": "📦 Backlog"},
                {"id": "list_456", "name": "🔨 In Progress"},
            ])
            mock_trello.get_cards_by_list = AsyncMock(return_value=[
                {"id": "card_a", "name": "Task A"},
                {"id": "card_b", "name": "Task B"},
            ])

            import asyncio
            result = asyncio.run(runner.start_run_by_name(
                list_name="📦 Backlog",
                trello_client=mock_trello,
            ))

            assert result is not None
            assert result.list_id == "list_123"
            assert result.list_name == "📦 Backlog"
            assert result.card_ids == ["card_a", "card_b"]
            assert result.status == SessionStatus.PENDING

    def test_start_run_by_name_not_found(self):
        """리스트 이름으로 정주행 시작 - 리스트 없음"""
        from seosoyoung.trello.list_runner import ListRunner, ListNotFoundError
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            # Mock trello client
            mock_trello = MagicMock()
            mock_trello.get_lists = AsyncMock(return_value=[
                {"id": "list_123", "name": "📦 Backlog"},
            ])

            import asyncio
            with pytest.raises(ListNotFoundError) as exc_info:
                asyncio.run(runner.start_run_by_name(
                    list_name="존재하지 않는 리스트",
                    trello_client=mock_trello,
                ))

            assert "존재하지 않는 리스트" in str(exc_info.value)

    def test_start_run_by_name_empty_list(self):
        """리스트 이름으로 정주행 시작 - 빈 리스트"""
        from seosoyoung.trello.list_runner import ListRunner, EmptyListError
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            # Mock trello client
            mock_trello = MagicMock()
            mock_trello.get_lists = AsyncMock(return_value=[
                {"id": "list_123", "name": "📦 Backlog"},
            ])
            mock_trello.get_cards_by_list = AsyncMock(return_value=[])

            import asyncio
            with pytest.raises(EmptyListError):
                asyncio.run(runner.start_run_by_name(
                    list_name="📦 Backlog",
                    trello_client=mock_trello,
                ))


class TestListRunMarkupParsing:
    """LIST_RUN 마크업 파싱 테스트"""

    def test_parse_list_run_markup_simple(self):
        """단순 LIST_RUN 마크업 파싱"""
        from seosoyoung.claude.runner import ClaudeRunner

        output = "정주행을 시작하겠습니다.\n<!-- LIST_RUN: 📦 Backlog -->"

        runner = ClaudeRunner()
        list_run = runner._extract_list_run_markup(output)

        assert list_run == "📦 Backlog"

    def test_parse_list_run_markup_with_spaces(self):
        """공백이 포함된 리스트명 파싱"""
        from seosoyoung.claude.runner import ClaudeRunner

        output = "<!-- LIST_RUN: 🔨 In Progress -->\n다른 내용"

        runner = ClaudeRunner()
        list_run = runner._extract_list_run_markup(output)

        assert list_run == "🔨 In Progress"

    def test_parse_list_run_markup_none(self):
        """마크업이 없는 경우"""
        from seosoyoung.claude.runner import ClaudeRunner

        output = "일반 응답입니다."

        runner = ClaudeRunner()
        list_run = runner._extract_list_run_markup(output)

        assert list_run is None

    def test_claude_result_has_list_run_field(self):
        """ClaudeResult에 list_run 필드 존재"""
        from seosoyoung.claude.runner import ClaudeResult

        result = ClaudeResult(
            success=True,
            output="test",
            list_run="📦 Backlog"
        )

        assert result.list_run == "📦 Backlog"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
