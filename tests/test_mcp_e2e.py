"""MCP 파일 첨부 E2E 통합 테스트

Phase 4: 전체 파이프라인 검증
- 멘션 → attach_file MCP 호출 → 슬랙 파일 첨부
- 트렐로 모드에서 첨부 파일 정상 전달
- 에러 케이스 (파일 없음, workspace 외부, 크기 초과)
- MCP 서버 독립 구동 (도구 등록, stdio 프로토콜)
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestMCPServerStandalone:
    """MCP 서버 독립 구동 테스트"""

    def test_server_instance_creation(self):
        """FastMCP 서버 인스턴스가 정상 생성됨"""
        from seosoyoung.mcp.server import mcp

        assert mcp.name == "seosoyoung-attach"

    def test_server_has_all_tools(self):
        """서버에 모든 도구가 등록됨"""
        from seosoyoung.mcp.server import mcp

        tools = list(mcp._tool_manager._tools.keys())
        assert "slack_attach_file" in tools
        assert "slack_get_context" in tools
        assert "slack_post_message" in tools
        assert "slack_generate_image" in tools
        assert "slack_download_thread_files" in tools
        assert "npc_list_characters" in tools
        assert "npc_open_session" in tools
        assert "npc_talk" in tools
        assert "npc_set_situation" in tools
        assert "npc_close_session" in tools
        assert "npc_get_history" in tools
        assert "npc_inject" in tools
        assert "slack_download_user_avatar" in tools
        assert "slack_get_user_profile" in tools
        assert "lore_keyword_search" in tools
        assert "lore_semantic_search" in tools
        assert "lore_chunk_read" in tools
        assert "lore_index_status" in tools
        assert len(tools) == 18

    def test_get_context_reads_env(self):
        """slack_get_context가 환경변수에서 값을 읽음"""
        with patch.dict(os.environ, {
            "SLACK_CHANNEL": "C_E2E_TEST",
            "SLACK_THREAD_TS": "9999999999.000001",
        }):
            from seosoyoung.mcp.tools.attach import get_slack_context

            result = get_slack_context()
            assert result["channel"] == "C_E2E_TEST"
            assert result["thread_ts"] == "9999999999.000001"


class TestMCPE2EMentionFlow:
    """멘션 → attach_file MCP 호출 → 슬랙 파일 첨부 E2E"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])

    def _make_workspace_file(self, suffix=".txt", content=b"E2E test file"):
        """workspace 내부에 테스트 파일 생성"""
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_full_attach_flow(self, mock_get_client):
        """전체 파일 첨부 플로우: 파일 생성 → MCP 도구 호출 → 슬랙 업로드"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(suffix=".md", content=b"# Test Report")
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_E2E_CHANNEL",
                thread_ts="1111111111.000001",
            )

            assert result["success"] is True
            assert "첨부 완료" in result["message"]

            # Slack API 호출 검증
            mock_client.files_upload_v2.assert_called_once()
            call_kwargs = mock_client.files_upload_v2.call_args
            assert call_kwargs.kwargs["channel"] == "C_E2E_CHANNEL"
            assert call_kwargs.kwargs["thread_ts"] == "1111111111.000001"
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_attach_yaml_file(self, mock_get_client):
        """YAML 파일 첨부 (대사 데이터 내보내기 시나리오)"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(
            suffix=".yaml",
            content=b"dialogues:\n  - id: test\n    text: hello",
        )
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_E2E_CHANNEL",
                thread_ts="1111111111.000002",
            )

            assert result["success"] is True
            mock_client.files_upload_v2.assert_called_once()
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_attach_xlsx_file(self, mock_get_client):
        """Excel 파일 첨부 (대사 엑셀 내보내기 시나리오)"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(
            suffix=".xlsx", content=b"PK\x03\x04fake-xlsx-content"
        )
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_E2E_CHANNEL",
                thread_ts="1111111111.000003",
            )

            assert result["success"] is True
        finally:
            os.unlink(tmp_path)


class TestMCPE2ETrelloFlow:
    """트렐로 모드에서 첨부 파일 정상 전달 E2E"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])

    def _make_workspace_file(self, suffix=".txt", content=b"trello test"):
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_runner_env_injection_for_trello(self):
        """트렐로 모드: _build_options에서 SLACK_CHANNEL/THREAD_TS가 env에 주입됨"""
        from seosoyoung.claude.agent_runner import ClaudeAgentRunner

        runner = ClaudeAgentRunner("2222222222.000001", channel="C_TRELLO_NOTIFY")
        options, _memory_prompt, _anchor_ts, _stderr_file = runner._build_options()

        assert options.env["SLACK_CHANNEL"] == "C_TRELLO_NOTIFY"
        assert options.env["SLACK_THREAD_TS"] == "2222222222.000001"

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_attach_in_trello_thread(self, mock_get_client):
        """트렐로 스레드에서 파일 첨부"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file(suffix=".json", content=b'{"result": "ok"}')
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_TRELLO_NOTIFY",
                thread_ts="2222222222.000001",
            )

            assert result["success"] is True
            call_kwargs = mock_client.files_upload_v2.call_args
            assert call_kwargs.kwargs["channel"] == "C_TRELLO_NOTIFY"
            assert call_kwargs.kwargs["thread_ts"] == "2222222222.000001"
        finally:
            os.unlink(tmp_path)

    def test_admin_config_has_mcp_for_trello(self):
        """admin 역할 config에 MCP 설정이 있어 트렐로 모드에서도 첨부 가능"""
        from seosoyoung.claude.executor import _get_role_config

        config = _get_role_config("admin")
        assert config["mcp_config_path"] is not None
        assert "mcp__seosoyoung-attach__slack_attach_file" in config["allowed_tools"]


class TestMCPE2EErrorCases:
    """E2E 에러 케이스 테스트"""

    WORKSPACE_ROOT = str(Path(__file__).resolve().parents[2])

    def _make_workspace_file(self, suffix=".txt", content=b"test"):
        tmp_dir = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            suffix=suffix, dir=str(tmp_dir), delete=False
        )
        tmp.write(content)
        tmp.close()
        return tmp.name

    def test_file_not_found_returns_error(self):
        """존재하지 않는 파일 → success=False"""
        from seosoyoung.mcp.tools.attach import attach_file

        result = attach_file(
            file_path="/absolutely/nonexistent/file.txt",
            channel="C12345",
            thread_ts="1234567890.123456",
        )
        assert result["success"] is False
        assert "존재하지 않" in result["message"]

    def test_workspace_outside_file_rejected(self):
        """workspace 외부 파일 → success=False"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"outside workspace")
            outside_path = tmp.name

        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=outside_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "workspace" in result["message"].lower() or "허용" in result["message"]
        finally:
            os.unlink(outside_path)

    def test_disallowed_extension_rejected(self):
        """허용되지 않는 확장자(.exe) → success=False"""
        tmp_path = self._make_workspace_file(suffix=".exe", content=b"MZ")
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "확장자" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_file_size_exceeded_rejected(self):
        """20MB 초과 파일 → success=False"""
        tmp_path = self._make_workspace_file(
            content=b"x" * (20 * 1024 * 1024 + 1)
        )
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C12345",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "크기" in result["message"] or "20MB" in result["message"]
        finally:
            os.unlink(tmp_path)

    @patch("seosoyoung.mcp.tools.attach._get_slack_client")
    def test_slack_api_failure_handled(self, mock_get_client):
        """Slack API 에러 → success=False, 에러 메시지 포함"""
        mock_client = MagicMock()
        mock_client.files_upload_v2.side_effect = Exception("channel_not_found")
        mock_get_client.return_value = mock_client

        tmp_path = self._make_workspace_file()
        try:
            from seosoyoung.mcp.tools.attach import attach_file

            result = attach_file(
                file_path=tmp_path,
                channel="C_INVALID",
                thread_ts="1234567890.123456",
            )
            assert result["success"] is False
            assert "channel_not_found" in result["message"]
        finally:
            os.unlink(tmp_path)

    def test_directory_path_rejected(self):
        """디렉토리 경로를 지정하면 거부"""
        dir_path = Path(self.WORKSPACE_ROOT) / ".local" / "tmp"
        dir_path.mkdir(parents=True, exist_ok=True)

        from seosoyoung.mcp.tools.attach import attach_file

        result = attach_file(
            file_path=str(dir_path),
            channel="C12345",
            thread_ts="1234567890.123456",
        )
        assert result["success"] is False
        assert "파일이 아님" in result["message"]


class TestMCPConfigIntegrity:
    """mcp_config.json과 봇 설정 정합성 E2E"""

    def test_mcp_config_server_name_matches(self):
        """mcp_config.json의 서버 이름이 FastMCP 서버와 일치"""
        config_path = Path(__file__).parent.parent / "mcp_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        from seosoyoung.mcp.server import mcp

        assert "seosoyoung-attach" in config
        assert mcp.name == "seosoyoung-attach"

    def test_allowed_tools_match_mcp_tool_names(self):
        """ROLE_TOOLS의 MCP 도구 패턴이 실제 도구 이름과 일치"""
        from seosoyoung.config import Config
        from seosoyoung.mcp.server import mcp

        admin_mcp_tools = [
            t for t in Config.ROLE_TOOLS["admin"]
            if t.startswith("mcp__seosoyoung-attach__")
        ]

        actual_tools = list(mcp._tool_manager._tools.keys())

        for tool_pattern in admin_mcp_tools:
            # mcp__seosoyoung-attach__slack_attach_file → slack_attach_file
            tool_name = tool_pattern.split("__")[-1]
            assert tool_name in actual_tools, f"{tool_name} not in MCP server tools"

    def test_default_allowed_tools_include_all_mcp_tools(self):
        """DEFAULT_ALLOWED_TOOLS에 MCP 도구 5개 모두 포함"""
        from seosoyoung.claude.agent_runner import DEFAULT_ALLOWED_TOOLS

        mcp_tools = [t for t in DEFAULT_ALLOWED_TOOLS if "seosoyoung-attach" in t]
        assert len(mcp_tools) == 11

    def test_viewer_has_no_mcp_tools(self):
        """viewer 역할에는 MCP 도구 없음"""
        from seosoyoung.config import Config

        viewer_tools = Config.ROLE_TOOLS["viewer"]
        mcp_tools = [t for t in viewer_tools if t.startswith("mcp__")]
        assert len(mcp_tools) == 0

    def test_mcp_config_env_vars_complete(self):
        """mcp_config.json에 필요한 환경변수 참조 포함"""
        config_path = Path(__file__).parent.parent / "mcp_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))

        env = config["seosoyoung-attach"]["env"]
        assert "SLACK_BOT_TOKEN" in env
        assert "SLACK_CHANNEL" in env
        assert "SLACK_THREAD_TS" in env
        assert "PYTHONPATH" in env
        assert "NPC_CLAUDE_API_KEY" in env

    def test_admin_role_includes_npc_tools(self):
        """admin 역할에 NPC 도구 6개 포함"""
        from seosoyoung.config import Config

        admin_tools = Config.ROLE_TOOLS["admin"]
        npc_tools = [t for t in admin_tools if "npc_" in t]
        assert len(npc_tools) == 6
        expected = {
            "mcp__seosoyoung-attach__npc_list_characters",
            "mcp__seosoyoung-attach__npc_open_session",
            "mcp__seosoyoung-attach__npc_talk",
            "mcp__seosoyoung-attach__npc_set_situation",
            "mcp__seosoyoung-attach__npc_close_session",
            "mcp__seosoyoung-attach__npc_get_history",
        }
        assert expected == set(npc_tools)


class TestNpcE2EFlow:
    """NPC 대화 E2E 통합 테스트: 세션 열기→대화→상황 변경→종료"""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """캐릭터 디렉토리와 프롬프트 템플릿을 임시 경로에 설정."""
        # 캐릭터 YAML
        char_dir = tmp_path / "characters"
        char_dir.mkdir()
        (char_dir / "fx.yaml").write_text(
            "id: fx\npriority: 1\n"
            "name:\n  kr: 펜릭스\n  en: Fenrix\n"
            "role:\n  kr: 주인공\n  en: Protagonist\n"
            "basic_info:\n  kr: 전사.\n  en: A warrior.\n"
            "personality:\n  kr:\n    - 용감함\n  en:\n    - Brave\n"
            "relationships:\n  items: []\n"
            "speech_guide:\n  kr: 거친 말투\n  en: Rough speech\n"
            'example_lines:\n  kr:\n    - "가자!"\n  en:\n    - "Let\'s go!"\n'
            "writing_guidelines:\n  kr:\n    - 항상 행동파\n  en:\n    - Always action-oriented\n",
            encoding="utf-8",
        )

        # 프롬프트 템플릿
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "npc_system.txt").write_text(
            "You are {name}, {role}.\n"
            "Personality: {personality}\n"
            "Speech: {speech_guide}\n"
            "Examples: {example_lines}\n"
            "Guidelines: {writing_guidelines}\n"
            "Info: {basic_info}\n"
            "Relations: {relationships}\n"
            "Situation: {situation}\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-e2e-key")

        # 모듈 내부 싱글턴/세션 초기화
        import seosoyoung.mcp.tools.npc_chat as npc_mod

        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        monkeypatch.setattr(npc_mod, "_loader_instance", loader)
        monkeypatch.setattr(
            npc_mod, "_DEFAULT_TEMPLATE_PATH", prompts_dir / "npc_system.txt"
        )
        npc_mod._sessions.clear()

    def test_full_conversation_flow(self):
        """전체 대화 플로우: 세션 열기→대화→상황 변경→이력 조회→종료"""
        from seosoyoung.mcp.tools.npc_chat import (
            npc_close_session,
            npc_get_history,
            npc_list_characters,
            npc_open_session,
            npc_set_situation,
            npc_talk,
        )

        # 1. 캐릭터 목록 조회
        chars = npc_list_characters()
        assert chars["success"] is True
        assert chars["count"] >= 1
        assert any(c["id"] == "fx" for c in chars["characters"])

        # 2. 세션 열기
        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="뭐야, 또 왔어?",
        ):
            open_result = npc_open_session("fx", situation="마을 입구")
        assert open_result["success"] is True
        sid = open_result["session_id"]
        assert open_result["message"] == "뭐야, 또 왔어?"

        # 3. 대화
        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="당연하지. 준비됐어.",
        ):
            talk1 = npc_talk(sid, "같이 가자!")
        assert talk1["success"] is True
        assert talk1["message"] == "당연하지. 준비됐어."
        assert talk1["turn_count"] == 3  # open(1) + talk(2)

        # 4. 상황 변경
        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="뭐야, 몬스터가 나타났어?!",
        ):
            sit = npc_set_situation(sid, "갑자기 몬스터가 출현")
        assert sit["success"] is True
        assert sit["situation"] == "갑자기 몬스터가 출현"

        # 5. 이력 조회 (세션 유지)
        history = npc_get_history(sid)
        assert history["success"] is True
        assert history["turn_count"] == 5  # open(1) + talk(2) + sit(2)
        assert history["has_digest"] is False

        # 6. 종료
        close = npc_close_session(sid)
        assert close["success"] is True
        assert close["turn_count"] == 5
        assert len(close["history"]) == 5

        # 7. 종료 후 대화 시도 → 실패
        fail = npc_talk(sid, "아직 있어?")
        assert fail["success"] is False

    def test_digest_compression_in_long_conversation(self, monkeypatch):
        """긴 대화에서 다이제스트 압축이 정상 동작하는지 확인"""
        from seosoyoung.mcp.tools.npc_chat import (
            DIGEST_KEEP_RECENT,
            DIGEST_THRESHOLD,
            _sessions,
            npc_get_history,
            npc_open_session,
            npc_talk,
        )

        call_count = 0

        def mock_call_claude(system, messages, max_tokens=1024):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Opening."
            # 다이제스트 요청인지 판별
            if "summarize" in system.lower() or "summarizer" in system.lower():
                return "Digest: long conversation about battle."
            return f"Reply {call_count}."

        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            side_effect=mock_call_claude,
        ):
            result = npc_open_session("fx")
            sid = result["session_id"]

            # threshold를 넘기 위해 많은 턴 대화
            for i in range(DIGEST_THRESHOLD):
                npc_talk(sid, f"Message {i}")

        # 다이제스트가 생성되었는지 확인
        history = npc_get_history(sid)
        assert history["has_digest"] is True
        # 압축 후 메시지 수는 원래 전체(open 2 + talk THRESHOLD*2)보다 적어야 함
        total_without_compress = 2 + DIGEST_THRESHOLD * 2
        assert history["turn_count"] < total_without_compress

    def test_error_invalid_character_id(self):
        """존재하지 않는 캐릭터 ID로 세션 열기 → 실패"""
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        result = npc_open_session("nonexistent_char_xyz")
        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]

    def test_error_expired_session_id(self):
        """만료된(종료된) 세션 ID로 대화/상황변경/이력조회 → 모두 실패"""
        from seosoyoung.mcp.tools.npc_chat import (
            npc_close_session,
            npc_get_history,
            npc_open_session,
            npc_set_situation,
            npc_talk,
        )

        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Hi.",
        ):
            result = npc_open_session("fx")
        sid = result["session_id"]
        npc_close_session(sid)

        # 모두 실패해야 함
        assert npc_talk(sid, "hello")["success"] is False
        assert npc_set_situation(sid, "new")["success"] is False
        assert npc_get_history(sid)["success"] is False
        assert npc_close_session(sid)["success"] is False

    def test_error_garbage_session_id(self):
        """완전히 무의미한 세션 ID → 실패"""
        from seosoyoung.mcp.tools.npc_chat import npc_talk

        result = npc_talk("garbage-id-12345", "hello")
        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]

    def test_english_language_session(self):
        """영어 세션이 정상 동작하는지 확인"""
        from seosoyoung.mcp.tools.npc_chat import npc_close_session, npc_open_session, npc_talk

        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Hey, you again?",
        ):
            result = npc_open_session("fx", language="en")
        assert result["success"] is True
        assert result["language"] == "en"
        sid = result["session_id"]

        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Sure, let's go.",
        ):
            talk = npc_talk(sid, "Let's fight!")
        assert talk["success"] is True

        close = npc_close_session(sid)
        assert close["success"] is True
        assert close["language"] == "en"
