"""ListRunner 테스트 - 리스트 정주행 기능"""

import json
import pytest
from pathlib import Path
import tempfile

import seosoyoung.slackbot.trello.watcher as _watcher_mod


class TestListRunSession:
    """ListRunSession 데이터 클래스 테스트"""

    def test_create_session(self):
        """세션 생성"""
        from seosoyoung.slackbot.trello.list_runner import ListRunSession, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import SessionStatus

        assert SessionStatus.PENDING.value == "pending"
        assert SessionStatus.RUNNING.value == "running"
        assert SessionStatus.PAUSED.value == "paused"
        assert SessionStatus.VERIFYING.value == "verifying"
        assert SessionStatus.COMPLETED.value == "completed"
        assert SessionStatus.FAILED.value == "failed"

    def test_session_to_dict(self):
        """세션 딕셔너리 변환"""
        from seosoyoung.slackbot.trello.list_runner import ListRunSession, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunSession, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            assert runner.sessions == {}
            assert runner.sessions_file.exists() is False

    def test_create_session(self):
        """새 세션 생성"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            retrieved = runner.get_session("nonexistent")
            assert retrieved is None

    def test_save_and_load_sessions(self):
        """세션 저장 및 로드"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            runner.create_session("list1", "List 1", ["card1"])
            runner.save_sessions()

            sessions_file = Path(tmpdir) / "list_run_sessions.json"
            assert sessions_file.exists()

    def test_sessions_file_content(self):
        """저장된 파일 내용 검증"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner

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
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
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
        from seosoyoung.slackbot.trello.list_runner import ListRunner, ListNotFoundError
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
        from seosoyoung.slackbot.trello.list_runner import ListRunner, EmptyListError
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

    def _extract_list_run(self, output: str):
        """LIST_RUN 마크업에서 리스트 이름 추출"""
        import re
        match = re.search(r"<!-- LIST_RUN: (.+?) -->", output)
        return match.group(1).strip() if match else None

    def test_parse_list_run_markup_simple(self):
        """단순 LIST_RUN 마크업 파싱"""
        output = "정주행을 시작하겠습니다.\n<!-- LIST_RUN: 📦 Backlog -->"
        assert self._extract_list_run(output) == "📦 Backlog"

    def test_parse_list_run_markup_with_spaces(self):
        """공백이 포함된 리스트명 파싱"""
        output = "<!-- LIST_RUN: 🔨 In Progress -->\n다른 내용"
        assert self._extract_list_run(output) == "🔨 In Progress"

    def test_parse_list_run_markup_none(self):
        """마크업이 없는 경우"""
        output = "일반 응답입니다."
        assert self._extract_list_run(output) is None

    def test_claude_result_has_list_run_field(self):
        """ClaudeResult에 list_run 필드 존재"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeResult

        result = ClaudeResult(
            success=True,
            output="test",
            list_run="📦 Backlog"
        )

        assert result.list_run == "📦 Backlog"


class TestCardExecution:
    """Phase 3: 카드 순차 실행 및 검증 세션 테스트"""

    def test_process_next_card_returns_card_info(self):
        """다음 카드 처리 시 카드 정보 반환"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a", "card_b", "card_c"],
            )
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            # Mock trello client
            mock_trello = MagicMock()
            mock_trello.get_card = AsyncMock(return_value={
                "id": "card_a",
                "name": "First Task",
                "desc": "Task description",
            })

            import asyncio
            result = asyncio.run(runner.process_next_card(
                session_id=session.session_id,
                trello_client=mock_trello,
            ))

            assert result is not None
            assert result["id"] == "card_a"
            assert result["name"] == "First Task"
            mock_trello.get_card.assert_called_once_with("card_a")

    def test_process_next_card_returns_none_when_done(self):
        """모든 카드 처리 완료 시 None 반환"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        from unittest.mock import MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)
            runner.mark_card_processed(session.session_id, "card_a", "completed")

            import asyncio
            result = asyncio.run(runner.process_next_card(
                session_id=session.session_id,
                trello_client=MagicMock(),
            ))

            assert result is None

    def test_execute_card_calls_workflow(self):
        """카드 실행 시 워크플로우 호출"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, CardExecutionResult
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )

            # Mock claude runner
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(return_value=MagicMock(
                success=True,
                output="작업 완료",
                session_id="session_xyz",
            ))

            card_info = {
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            }

            import asyncio
            result = asyncio.run(runner.execute_card(
                session_id=session.session_id,
                card_info=card_info,
                claude_runner=mock_claude,
            ))

            assert result.success is True
            assert result.card_id == "card_a"
            mock_claude.run.assert_called_once()

    def test_execute_card_handles_failure(self):
        """카드 실행 실패 처리"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, CardExecutionResult
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )

            # Mock claude runner that fails
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(return_value=MagicMock(
                success=False,
                output="",
                error="Timeout",
            ))

            card_info = {
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            }

            import asyncio
            result = asyncio.run(runner.execute_card(
                session_id=session.session_id,
                card_info=card_info,
                claude_runner=mock_claude,
            ))

            assert result.success is False
            assert result.error == "Timeout"


class TestValidationSession:
    """검증 세션 테스트"""

    def test_validate_completion_pass(self):
        """검증 세션 통과"""
        from seosoyoung.slackbot.trello.list_runner import (
            ListRunner, ValidationResult, ValidationStatus
        )
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )

            # Mock claude runner returning PASS
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(return_value=MagicMock(
                success=True,
                output="검증 결과입니다.\nVALIDATION_RESULT: PASS\n모든 항목 통과",
                session_id="verify_session",
            ))

            card_info = {
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            }

            import asyncio
            result = asyncio.run(runner.validate_completion(
                session_id=session.session_id,
                card_info=card_info,
                execution_output="작업 완료",
                claude_runner=mock_claude,
            ))

            assert result.status == ValidationStatus.PASS
            assert result.card_id == "card_a"

    def test_validate_completion_fail(self):
        """검증 세션 실패"""
        from seosoyoung.slackbot.trello.list_runner import (
            ListRunner, ValidationResult, ValidationStatus
        )
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )

            # Mock claude runner returning FAIL
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(return_value=MagicMock(
                success=True,
                output="검증 실패.\nVALIDATION_RESULT: FAIL\n테스트 미통과",
                session_id="verify_session",
            ))

            card_info = {
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            }

            import asyncio
            result = asyncio.run(runner.validate_completion(
                session_id=session.session_id,
                card_info=card_info,
                execution_output="작업 완료",
                claude_runner=mock_claude,
            ))

            assert result.status == ValidationStatus.FAIL
            assert "테스트 미통과" in result.output

    def test_validate_completion_no_marker(self):
        """검증 결과 마커가 없는 경우 UNKNOWN 처리"""
        from seosoyoung.slackbot.trello.list_runner import (
            ListRunner, ValidationResult, ValidationStatus
        )
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )

            # Mock claude runner without VALIDATION_RESULT marker
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(return_value=MagicMock(
                success=True,
                output="검증을 수행했습니다. 결과가 명확하지 않습니다.",
                session_id="verify_session",
            ))

            card_info = {
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            }

            import asyncio
            result = asyncio.run(runner.validate_completion(
                session_id=session.session_id,
                card_info=card_info,
                execution_output="작업 완료",
                claude_runner=mock_claude,
            ))

            assert result.status == ValidationStatus.UNKNOWN


class TestValidationResultParsing:
    """검증 결과 파싱 테스트"""

    def test_parse_validation_result_pass(self):
        """PASS 결과 파싱"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, ValidationStatus

        output = "검증 완료.\nVALIDATION_RESULT: PASS\n모든 테스트 통과"
        result = ListRunner._parse_validation_result(output)
        assert result == ValidationStatus.PASS

    def test_parse_validation_result_fail(self):
        """FAIL 결과 파싱"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, ValidationStatus

        output = "VALIDATION_RESULT: FAIL\n일부 테스트 실패"
        result = ListRunner._parse_validation_result(output)
        assert result == ValidationStatus.FAIL

    def test_parse_validation_result_case_insensitive(self):
        """대소문자 구분 없이 파싱"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, ValidationStatus

        output1 = "validation_result: pass"
        output2 = "VALIDATION_RESULT: pass"
        output3 = "Validation_Result: PASS"

        assert ListRunner._parse_validation_result(output1) == ValidationStatus.PASS
        assert ListRunner._parse_validation_result(output2) == ValidationStatus.PASS
        assert ListRunner._parse_validation_result(output3) == ValidationStatus.PASS

    def test_parse_validation_result_unknown(self):
        """마커가 없는 경우 UNKNOWN"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, ValidationStatus

        output = "검증을 수행했지만 결과 마커가 없습니다."
        result = ListRunner._parse_validation_result(output)
        assert result == ValidationStatus.UNKNOWN


class TestFullExecutionFlow:
    """전체 실행 플로우 테스트"""

    def test_run_next_with_validation(self):
        """카드 실행 후 검증까지 전체 플로우"""
        from seosoyoung.slackbot.trello.list_runner import (
            ListRunner, SessionStatus, ValidationStatus
        )
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            # Mock trello client
            mock_trello = MagicMock()
            mock_trello.get_card = AsyncMock(return_value={
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            })

            # Mock claude runner - 실행과 검증 모두 성공
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(side_effect=[
                # First call: execution
                MagicMock(success=True, output="작업 완료", session_id="exec_session"),
                # Second call: validation
                MagicMock(success=True, output="VALIDATION_RESULT: PASS", session_id="verify_session"),
            ])

            import asyncio
            result = asyncio.run(runner.run_next_card(
                session_id=session.session_id,
                trello_client=mock_trello,
                claude_runner=mock_claude,
            ))

            assert result.execution_success is True
            assert result.validation_status == ValidationStatus.PASS
            assert result.card_id == "card_a"

            # 카드가 처리 완료로 표시되었는지 확인
            updated_session = runner.get_session(session.session_id)
            assert "card_a" in updated_session.processed_cards


class TestPauseRun:
    """Phase 4: 중단 기능 테스트"""

    def test_pause_run_changes_status_to_paused(self):
        """pause_run 호출 시 상태가 PAUSED로 변경"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a", "card_b"],
            )
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            result = runner.pause_run(
                session_id=session.session_id,
                reason="검증 실패로 중단",
            )

            assert result is True
            updated = runner.get_session(session.session_id)
            assert updated.status == SessionStatus.PAUSED
            assert updated.error_message == "검증 실패로 중단"

    def test_pause_run_invalid_session(self):
        """존재하지 않는 세션 중단 시도"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            result = runner.pause_run(
                session_id="nonexistent",
                reason="테스트",
            )

            assert result is False

    def test_pause_run_from_verifying_state(self):
        """VERIFYING 상태에서도 중단 가능"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.VERIFYING)

            result = runner.pause_run(
                session_id=session.session_id,
                reason="검증 중 오류",
            )

            assert result is True
            assert runner.get_session(session.session_id).status == SessionStatus.PAUSED

    def test_pause_run_from_completed_state_fails(self):
        """COMPLETED 상태에서는 중단 불가"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.COMPLETED)

            result = runner.pause_run(
                session_id=session.session_id,
                reason="완료된 세션 중단 시도",
            )

            assert result is False
            # 상태 변경 없음
            assert runner.get_session(session.session_id).status == SessionStatus.COMPLETED


class TestResumeRun:
    """Phase 4: 재개 기능 테스트"""

    def test_resume_run_changes_status_to_running(self):
        """resume_run 호출 시 상태가 RUNNING으로 변경"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a", "card_b"],
            )
            runner.update_session_status(session.session_id, SessionStatus.PAUSED)

            result = runner.resume_run(session_id=session.session_id)

            assert result is True
            updated = runner.get_session(session.session_id)
            assert updated.status == SessionStatus.RUNNING
            # 에러 메시지 초기화
            assert updated.error_message is None

    def test_resume_run_invalid_session(self):
        """존재하지 않는 세션 재개 시도"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            result = runner.resume_run(session_id="nonexistent")

            assert result is False

    def test_resume_run_from_running_state_fails(self):
        """이미 RUNNING 상태에서는 재개 불가 (이미 실행 중)"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            result = runner.resume_run(session_id=session.session_id)

            assert result is False

    def test_resume_run_from_completed_state_fails(self):
        """COMPLETED 상태에서는 재개 불가"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.COMPLETED)

            result = runner.resume_run(session_id=session.session_id)

            assert result is False

    def test_resume_run_from_failed_state(self):
        """FAILED 상태에서도 재개 가능 (재시도)"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.FAILED)

            result = runner.resume_run(session_id=session.session_id)

            assert result is True
            assert runner.get_session(session.session_id).status == SessionStatus.RUNNING


class TestGetPausedSessions:
    """중단된 세션 조회 테스트"""

    def test_get_paused_sessions(self):
        """PAUSED 상태인 세션만 조회"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            # 여러 세션 생성
            s1 = runner.create_session("list1", "List 1", ["card1"])
            s2 = runner.create_session("list2", "List 2", ["card2"])
            s3 = runner.create_session("list3", "List 3", ["card3"])

            # 상태 변경
            runner.update_session_status(s1.session_id, SessionStatus.RUNNING)
            runner.update_session_status(s2.session_id, SessionStatus.PAUSED)
            runner.update_session_status(s3.session_id, SessionStatus.PAUSED)

            paused = runner.get_paused_sessions()

            assert len(paused) == 2
            session_ids = [s.session_id for s in paused]
            assert s2.session_id in session_ids
            assert s3.session_id in session_ids


class TestFindSessionByListName:
    """리스트 이름으로 세션 검색 테스트"""

    def test_find_session_by_list_name(self):
        """리스트 이름으로 활성 세션 검색"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.PAUSED)

            found = runner.find_session_by_list_name("📦 Backlog")

            assert found is not None
            assert found.session_id == session.session_id

    def test_find_session_by_list_name_not_found(self):
        """존재하지 않는 리스트 이름 검색"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            found = runner.find_session_by_list_name("존재하지 않는 리스트")

            assert found is None

    def test_find_session_by_list_name_excludes_completed(self):
        """COMPLETED 세션은 검색 제외"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))

            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )
            runner.update_session_status(session.session_id, SessionStatus.COMPLETED)

            found = runner.find_session_by_list_name("📦 Backlog")

            assert found is None


class TestStateTransitions:
    """상태 전환 테스트"""

    def test_valid_state_transitions(self):
        """유효한 상태 전환"""
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a"],
            )

            # PENDING -> RUNNING
            assert session.status == SessionStatus.PENDING
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)
            assert runner.get_session(session.session_id).status == SessionStatus.RUNNING

            # RUNNING -> PAUSED (via pause_run)
            runner.pause_run(session.session_id, "테스트 중단")
            assert runner.get_session(session.session_id).status == SessionStatus.PAUSED

            # PAUSED -> RUNNING (via resume_run)
            runner.resume_run(session.session_id)
            assert runner.get_session(session.session_id).status == SessionStatus.RUNNING

            # RUNNING -> VERIFYING
            runner.update_session_status(session.session_id, SessionStatus.VERIFYING)
            assert runner.get_session(session.session_id).status == SessionStatus.VERIFYING

            # VERIFYING -> RUNNING
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)
            assert runner.get_session(session.session_id).status == SessionStatus.RUNNING

            # RUNNING -> COMPLETED
            runner.update_session_status(session.session_id, SessionStatus.COMPLETED)
            assert runner.get_session(session.session_id).status == SessionStatus.COMPLETED


class TestRunNextWithPause:
    """run_next_card에서 검증 실패 시 자동 중단 테스트"""

    def test_run_next_pauses_on_validation_fail(self):
        """검증 실패 시 자동으로 세션 중단"""
        from seosoyoung.slackbot.trello.list_runner import (
            ListRunner, SessionStatus, ValidationStatus
        )
        from unittest.mock import AsyncMock, MagicMock

        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ListRunner(data_dir=Path(tmpdir))
            session = runner.create_session(
                list_id="list_123",
                list_name="📦 Backlog",
                card_ids=["card_a", "card_b"],
            )
            runner.update_session_status(session.session_id, SessionStatus.RUNNING)

            # Mock trello client
            mock_trello = MagicMock()
            mock_trello.get_card = AsyncMock(return_value={
                "id": "card_a",
                "name": "Test Task",
                "desc": "Do something",
            })

            # Mock claude runner - 실행 성공, 검증 실패
            mock_claude = MagicMock()
            mock_claude.run = AsyncMock(side_effect=[
                # First call: execution
                MagicMock(success=True, output="작업 완료", session_id="exec_session"),
                # Second call: validation - FAIL
                MagicMock(success=True, output="VALIDATION_RESULT: FAIL\n테스트 실패", session_id="verify_session"),
            ])

            import asyncio
            result = asyncio.run(runner.run_next_card(
                session_id=session.session_id,
                trello_client=mock_trello,
                claude_runner=mock_claude,
                auto_pause_on_fail=True,
            ))

            assert result.validation_status == ValidationStatus.FAIL

            # 세션이 PAUSED 상태여야 함
            updated_session = runner.get_session(session.session_id)
            assert updated_session.status == SessionStatus.PAUSED
            assert "검증 실패" in (updated_session.error_message or "")


class TestRunListLabelTrigger:
    """Phase 5: 트렐로 레이블 트리거 테스트 (🏃 Run List)"""

    def test_has_run_list_label_returns_true(self):
        """🏃 Run List 레이블 있는 카드 감지"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        card = TrelloCard(
            id="card_123",
            name="Test Card",
            desc="",
            url="",
            list_id="list_abc",
            labels=[
                {"id": "label_1", "name": "🏃 Run List", "color": "green"},
            ],
        )

        assert watcher._has_run_list_label(card) is True

    def test_has_run_list_label_returns_false(self):
        """🏃 Run List 레이블 없는 카드"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )

        card = TrelloCard(
            id="card_123",
            name="Test Card",
            desc="",
            url="",
            list_id="list_abc",
            labels=[
                {"id": "label_1", "name": "Execute", "color": "red_dark"},
            ],
        )

        assert watcher._has_run_list_label(card) is False


class TestTrelloClientRemoveLabel:
    """TrelloClient 레이블 제거 메서드 테스트"""

    def test_remove_label_from_card_success(self):
        """카드에서 레이블 제거 성공"""
        from seosoyoung.slackbot.trello.client import TrelloClient
        from unittest.mock import MagicMock, patch

        client = TrelloClient(api_key="test_key", token="test_token")

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = {}

            result = client.remove_label_from_card("card_123", "label_456")

            assert result is True
            mock_request.assert_called_once_with(
                "DELETE",
                "/cards/card_123/idLabels/label_456"
            )

    def test_remove_label_from_card_failure(self):
        """카드에서 레이블 제거 실패"""
        from seosoyoung.slackbot.trello.client import TrelloClient
        from unittest.mock import MagicMock, patch

        client = TrelloClient(api_key="test_key", token="test_token")

        with patch.object(client, "_request") as mock_request:
            mock_request.return_value = None

            result = client.remove_label_from_card("card_123", "label_456")

            assert result is False


class TestCheckRunListLabels:
    """_check_run_list_labels() 메서드 테스트"""

    def test_check_run_list_labels_triggers_list_run(self):
        """🏃 Run List 레이블 발견 시 리스트 정주행 시작"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock, patch

        mock_trello = MagicMock()

        # 리스트에 3개의 카드, 첫 번째만 🏃 Run List 레이블 있음
        mock_trello.get_lists.return_value = [
            {"id": "list_backlog", "name": "📦 Backlog"},
        ]
        mock_trello.get_cards_in_list.return_value = [
            TrelloCard(
                id="card_1",
                name="First Card",
                desc="",
                url="https://trello.com/c/abc",
                list_id="list_backlog",
                labels=[{"id": "run_label", "name": "🏃 Run List", "color": "green"}],
            ),
            TrelloCard(
                id="card_2",
                name="Second Card",
                desc="",
                url="https://trello.com/c/def",
                list_id="list_backlog",
                labels=[],
            ),
            TrelloCard(
                id="card_3",
                name="Third Card",
                desc="",
                url="https://trello.com/c/ghi",
                list_id="list_backlog",
                labels=[],
            ),
        ]

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )
        watcher.trello = mock_trello

        with patch.object(watcher, "_start_list_run") as mock_start:
            watcher._check_run_list_labels()

            # _start_list_run이 호출되어야 함
            mock_start.assert_called_once()
            call_args = mock_start.call_args
            # 첫 번째 인자: list_id, list_name, cards
            assert call_args[0][0] == "list_backlog"
            assert call_args[0][1] == "📦 Backlog"
            assert len(call_args[0][2]) == 3  # 전체 카드 목록

    def test_check_run_list_labels_removes_label(self):
        """레이블 감지 후 첫 카드에서 레이블 제거"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock, patch

        mock_trello = MagicMock()
        mock_trello.get_lists.return_value = [
            {"id": "list_backlog", "name": "📦 Backlog"},
        ]
        mock_trello.get_cards_in_list.return_value = [
            TrelloCard(
                id="card_1",
                name="First Card",
                desc="",
                url="",
                list_id="list_backlog",
                labels=[{"id": "run_label_id", "name": "🏃 Run List", "color": "green"}],
            ),
        ]
        mock_trello.remove_label_from_card.return_value = True

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )
        watcher.trello = mock_trello

        with patch.object(watcher, "_start_list_run"):
            watcher._check_run_list_labels()

            # 레이블 제거 호출 확인
            mock_trello.remove_label_from_card.assert_called_once_with(
                "card_1", "run_label_id"
            )

    def test_check_run_list_labels_no_trigger(self):
        """🏃 Run List 레이블 없으면 정주행 시작 안 함"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock, patch

        mock_trello = MagicMock()
        mock_trello.get_lists.return_value = [
            {"id": "list_backlog", "name": "📦 Backlog"},
        ]
        mock_trello.get_cards_in_list.return_value = [
            TrelloCard(
                id="card_1",
                name="First Card",
                desc="",
                url="",
                list_id="list_backlog",
                labels=[],  # 레이블 없음
            ),
        ]

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
        )
        watcher.trello = mock_trello

        with patch.object(watcher, "_start_list_run") as mock_start:
            watcher._check_run_list_labels()

            # _start_list_run이 호출되지 않아야 함
            mock_start.assert_not_called()


class TestStartListRunIntegration:
    """_start_list_run() 통합 테스트"""

    def test_start_list_run_creates_session(self):
        """_start_list_run 호출 시 ListRunner 세션 생성"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.list_runner import ListRunner, SessionStatus
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock, patch

        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))

            mock_slack = MagicMock()
            mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
            )

            cards = [
                TrelloCard(
                    id="card_1",
                    name="First Card",
                    desc="",
                    url="https://trello.com/c/abc",
                    list_id="list_backlog",
                    labels=[],
                ),
                TrelloCard(
                    id="card_2",
                    name="Second Card",
                    desc="",
                    url="https://trello.com/c/def",
                    list_id="list_backlog",
                    labels=[],
                ),
            ]

            # _process_list_run_card를 모킹하여 실제 Claude 실행 방지
            with patch.object(watcher, "_process_list_run_card"):
                watcher._start_list_run("list_backlog", "📦 Backlog", cards)

            # 세션이 생성되었는지 확인
            sessions = list(list_runner.sessions.values())
            assert len(sessions) == 1
            session = sessions[0]
            assert session.list_id == "list_backlog"
            assert session.list_name == "📦 Backlog"
            assert session.card_ids == ["card_1", "card_2"]
            assert session.status == SessionStatus.PENDING

    def test_start_list_run_without_list_runner(self):
        """ListRunner 없이 _start_list_run 호출 시 경고 로그"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock

        watcher = TrelloWatcher(
            slack_client=MagicMock(),
            session_manager=MagicMock(),
            claude_runner_factory=MagicMock(),
            list_runner_ref=None,  # ListRunner 없음
        )

        cards = [
            TrelloCard(
                id="card_1",
                name="First Card",
                desc="",
                url="",
                list_id="list_backlog",
                labels=[],
            ),
        ]

        # 예외 없이 종료되어야 함 (경고 로그만)
        watcher._start_list_run("list_backlog", "📦 Backlog", cards)

    def test_start_list_run_sends_slack_notification(self):
        """_start_list_run 호출 시 슬랙 알림 전송"""
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.list_runner import ListRunner
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock, patch, call

        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))

            mock_slack = MagicMock()
            mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

            watcher = TrelloWatcher(
                slack_client=mock_slack,
                session_manager=MagicMock(),
                claude_runner_factory=MagicMock(),
                list_runner_ref=lambda: list_runner,
                notify_channel="C12345",
            )

            cards = [
                TrelloCard(
                    id="card_1",
                    name="First Card",
                    desc="",
                    url="",
                    list_id="list_backlog",
                    labels=[],
                ),
            ]

            with patch.object(watcher, "_process_list_run_card"), \
                 patch.object(_watcher_mod.Config.trello, 'dm_target_user_id', ""):
                watcher._start_list_run("list_backlog", "📦 Backlog", cards)

            # 슬랙 알림이 전송되었는지 확인
            mock_slack.chat_postMessage.assert_called_once()
            call_kwargs = mock_slack.chat_postMessage.call_args[1]
            assert call_kwargs["channel"] == "C12345"
            assert "📦 Backlog" in call_kwargs["text"]
            assert "1개" in call_kwargs["text"]


class TestHandleListRunMarkerIntegration:
    """_handle_list_run_marker() 통합 테스트"""

    def test_handle_list_run_marker_starts_list_run(self):
        """LIST_RUN 마커 처리 시 정주행 시작"""
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from seosoyoung.slackbot.trello.list_runner import ListRunner
        from seosoyoung.slackbot.trello.client import TrelloCard
        from unittest.mock import MagicMock, patch

        with tempfile.TemporaryDirectory() as tmpdir:
            list_runner = ListRunner(data_dir=Path(tmpdir))

            mock_trello = MagicMock()
            mock_trello.get_lists.return_value = [
                {"id": "list_123", "name": "📦 Backlog"},
            ]
            mock_trello.get_cards_in_list.return_value = [
                TrelloCard(
                    id="card_a",
                    name="Task A",
                    desc="",
                    url="",
                    list_id="list_123",
                    labels=[],
                ),
            ]

            mock_slack = MagicMock()
            mock_slack.chat_postMessage.return_value = {"ts": "1234567890.123456"}

            mock_watcher = MagicMock(spec=TrelloWatcher)
            mock_watcher.trello = mock_trello

            executor = ClaudeExecutor(
                session_manager=MagicMock(),
                get_session_lock=MagicMock(),
                mark_session_running=MagicMock(),
                mark_session_stopped=MagicMock(),
                get_running_session_count=MagicMock(return_value=1),
                restart_manager=MagicMock(),
                send_long_message=MagicMock(),
                send_restart_confirmation=MagicMock(),
                trello_watcher_ref=lambda: mock_watcher,
                list_runner_ref=lambda: list_runner,
            )

            mock_say = MagicMock()

            executor._handle_list_run_marker(
                list_name="📦 Backlog",
                channel="C12345",
                thread_ts="1234567890.123456",
                say=mock_say,
                client=mock_slack,
            )

            # TrelloWatcher._start_list_run이 호출되었는지 확인
            mock_watcher._start_list_run.assert_called_once()

    def test_handle_list_run_marker_without_watcher(self):
        """TrelloWatcher 없이 LIST_RUN 마커 처리 시 에러 메시지"""
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from unittest.mock import MagicMock

        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            get_session_lock=MagicMock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=1),
            restart_manager=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            trello_watcher_ref=None,  # 워처 없음
            list_runner_ref=None,
        )

        mock_say = MagicMock()

        executor._handle_list_run_marker(
            list_name="📦 Backlog",
            channel="C12345",
            thread_ts="1234567890.123456",
            say=mock_say,
            client=MagicMock(),
        )

        # 에러 메시지가 전송되었는지 확인
        mock_say.assert_called_once()
        call_args = mock_say.call_args
        assert "TrelloWatcher" in call_args[1]["text"]

    def test_handle_list_run_marker_list_not_found(self):
        """존재하지 않는 리스트로 LIST_RUN 마커 처리 시 에러 메시지"""
        from seosoyoung.slackbot.claude.executor import ClaudeExecutor
        from seosoyoung.slackbot.trello.watcher import TrelloWatcher
        from unittest.mock import MagicMock

        mock_trello = MagicMock()
        mock_trello.get_lists.return_value = [
            {"id": "list_123", "name": "📦 Backlog"},
        ]

        mock_watcher = MagicMock(spec=TrelloWatcher)
        mock_watcher.trello = mock_trello

        executor = ClaudeExecutor(
            session_manager=MagicMock(),
            get_session_lock=MagicMock(),
            mark_session_running=MagicMock(),
            mark_session_stopped=MagicMock(),
            get_running_session_count=MagicMock(return_value=1),
            restart_manager=MagicMock(),
            send_long_message=MagicMock(),
            send_restart_confirmation=MagicMock(),
            trello_watcher_ref=lambda: mock_watcher,
            list_runner_ref=None,
        )

        mock_say = MagicMock()

        executor._handle_list_run_marker(
            list_name="존재하지 않는 리스트",
            channel="C12345",
            thread_ts="1234567890.123456",
            say=mock_say,
            client=MagicMock(),
        )

        # 에러 메시지가 전송되었는지 확인
        mock_say.assert_called_once()
        call_args = mock_say.call_args
        assert "찾을 수 없습니다" in call_args[1]["text"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
