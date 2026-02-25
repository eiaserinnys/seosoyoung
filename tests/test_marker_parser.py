"""marker_parser 모듈 테스트

MarkerParser가 claude/ 밖에서 동작하며,
응용 마커(UPDATE, RESTART, LIST_RUN)를 올바르게 파싱하는지 검증.
"""

import pytest


class TestParsedMarkers:
    """ParsedMarkers 데이터 클래스 테스트"""

    def test_default_values(self):
        """기본값이 모두 False/None"""
        from seosoyoung.slackbot.marker_parser import ParsedMarkers

        markers = ParsedMarkers()
        assert markers.update_requested is False
        assert markers.restart_requested is False
        assert markers.list_run is None


class TestParseMarkers:
    """parse_markers() 함수 테스트"""

    def test_no_markers(self):
        """마커가 없는 일반 텍스트"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        result = parse_markers("Hello, this is a normal response.")
        assert result.update_requested is False
        assert result.restart_requested is False
        assert result.list_run is None

    def test_update_marker(self):
        """<!-- UPDATE --> 마커 감지"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        result = parse_markers("Done! <!-- UPDATE -->")
        assert result.update_requested is True
        assert result.restart_requested is False

    def test_restart_marker(self):
        """<!-- RESTART --> 마커 감지"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        result = parse_markers("Restarting... <!-- RESTART -->")
        assert result.restart_requested is True
        assert result.update_requested is False

    def test_list_run_marker(self):
        """<!-- LIST_RUN: 리스트명 --> 마커 감지"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        result = parse_markers("Processing <!-- LIST_RUN: 📦 Backlog -->")
        assert result.list_run == "📦 Backlog"

    def test_list_run_marker_with_whitespace(self):
        """LIST_RUN 마커에 공백이 있어도 strip 처리"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        result = parse_markers("<!-- LIST_RUN:   🚀 To Go   -->")
        assert result.list_run == "🚀 To Go"

    def test_multiple_markers(self):
        """복합 마커가 모두 감지된다"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        text = "Done! <!-- UPDATE --> <!-- RESTART --> <!-- LIST_RUN: ✅ Done -->"
        result = parse_markers(text)
        assert result.update_requested is True
        assert result.restart_requested is True
        assert result.list_run == "✅ Done"

    def test_empty_output(self):
        """빈 문자열"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        result = parse_markers("")
        assert result.update_requested is False
        assert result.restart_requested is False
        assert result.list_run is None

    def test_marker_in_middle_of_text(self):
        """텍스트 중간에 있는 마커도 감지"""
        from seosoyoung.slackbot.marker_parser import parse_markers

        text = "작업 완료했습니다. <!-- UPDATE --> 더 궁금한 점이 있으시면 말씀해주세요."
        result = parse_markers(text)
        assert result.update_requested is True


class TestMarkerParserModuleLocation:
    """MarkerParser가 claude/ 밖에 위치하는지 검증"""

    def test_import_from_slackbot(self):
        """slackbot.marker_parser로 import 가능"""
        from seosoyoung.slackbot.marker_parser import parse_markers, ParsedMarkers
        assert parse_markers is not None
        assert ParsedMarkers is not None

    def test_not_in_claude_package(self):
        """marker_parser가 claude/ 패키지 안에 없어야 한다"""
        import importlib
        try:
            importlib.import_module("seosoyoung.slackbot.claude.marker_parser")
            pytest.fail("marker_parser가 claude/ 안에 있으면 안 됩니다")
        except ImportError:
            pass  # 올바른 동작


class TestClaudeResultCompat:
    """ClaudeResult가 EngineResult 기반으로 동작하는지 검증"""

    def test_claude_result_inherits_engine_result(self):
        """ClaudeResult가 EngineResult의 서브클래스"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        assert issubclass(ClaudeResult, EngineResult)

    def test_claude_result_has_marker_fields(self):
        """ClaudeResult에 응용 마커 필드가 있다 (하위호환)"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeResult

        result = ClaudeResult(
            success=True,
            output="test",
            update_requested=True,
            restart_requested=False,
            list_run="📦 Backlog",
            anchor_ts="1234.5678",
        )
        assert result.update_requested is True
        assert result.list_run == "📦 Backlog"
        assert result.anchor_ts == "1234.5678"

    def test_from_engine_result(self):
        """EngineResult + ParsedMarkers → ClaudeResult 변환"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
        from seosoyoung.slackbot.claude.engine_types import EngineResult
        from seosoyoung.slackbot.marker_parser import ParsedMarkers

        engine_result = EngineResult(
            success=True,
            output="Hello <!-- UPDATE -->",
            session_id="sess-001",
            collected_messages=[{"role": "assistant", "content": "Hello"}],
        )
        markers = ParsedMarkers(update_requested=True)

        claude_result = ClaudeResult.from_engine_result(engine_result, markers)
        assert claude_result.success is True
        assert claude_result.output == "Hello <!-- UPDATE -->"
        assert claude_result.session_id == "sess-001"
        assert claude_result.update_requested is True
        assert claude_result.restart_requested is False
        assert claude_result.collected_messages == engine_result.collected_messages

    def test_from_engine_result_with_anchor_ts(self):
        """anchor_ts가 올바르게 전달되는지"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        engine_result = EngineResult(success=True, output="test")
        claude_result = ClaudeResult.from_engine_result(
            engine_result, anchor_ts="1234.5678"
        )
        assert claude_result.anchor_ts == "1234.5678"

    def test_from_engine_result_default_markers(self):
        """markers=None일 때 기본값 적용"""
        from seosoyoung.slackbot.claude.agent_runner import ClaudeResult
        from seosoyoung.slackbot.claude.engine_types import EngineResult

        engine_result = EngineResult(success=True, output="test")
        claude_result = ClaudeResult.from_engine_result(engine_result)
        assert claude_result.update_requested is False
        assert claude_result.restart_requested is False
        assert claude_result.list_run is None
        assert claude_result.anchor_ts == ""
