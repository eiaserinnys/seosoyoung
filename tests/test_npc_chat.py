"""NPC 대화 모듈 단위 테스트 (캐릭터 로더, 프롬프트 빌더, 세션 관리, MCP 도구)"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 테스트용 캐릭터 YAML 데이터 (hn.yaml 형식 기반)
SAMPLE_CHARACTER_YAML = """\
id: hn
priority: 4

name:
  kr: 하니엘
  en: Haniel

role:
  _display: inline
  kr: 천사, 펜릭스 부활 담당
  en: Angel, in charge of Fenrix's resurrection

title:
  _display: inline
  kr: 피와 계약의 천사
  en: Angel of Blood and Pact

tagline:
  _display: inline
  kr: "흐음~ 누가 부활시켜주면 해야 할 말이 있지 않나?"
  en: "Hmm~ Shouldn't you say something to the one who resurrected you?"

basic_info:
  _title:
    kr: 기본 정보
    en: Basic Info
  _display: markdown
  kr: |
    칼리엘의 사실상 조수 역할을 하는 천사.
  en: |
    An angel who effectively serves as Kaliel's assistant.

personality:
  _title:
    kr: 성격
    en: Personality
  _display: list
  kr:
    - 게으르고 의욕이 없다
    - 냉소적이고 비딱한 태도
  en:
    - Lazy and unmotivated
    - Cynical and twisted attitude

relationships:
  _title:
    kr: 관계
    en: Relationships
  _display: table
  _columns:
    kr: [인물, 관계]
    en: [Character, Relationship]
  items:
    - character:
        kr: 펜릭스
        en: Fenrix
      relation:
        kr: 귀찮은 듯 대하지만 매번 부활시켜줌
        en: Acts annoyed but resurrects him every time

speech_guide:
  _title:
    kr: 말투 가이드
    en: Speech Guide
  _display: markdown
  kr: |
    **톤:** 시니컬, 귀찮아하는 듯한
    **격식:** 반말 (펜릭스에게)
  en: |
    **Tone:** Cynical, seemingly annoyed
    **Formality:** Casual (to Fenrix)

example_lines:
  _title:
    kr: 대표 대사
    en: Example Lines
  _display: list
  kr:
    - "너무 멀리 가지마. 길 잃어버린다."
    - "헐, 안 죽고 돌아왔네."
  en:
    - "Don't wander off and get lost now."
    - "Oh wow, you're back alive."

writing_guidelines:
  _title:
    kr: 작성 시 주의사항
    en: Writing Guidelines
  _display: list
  kr:
    - 세상의 종말에 대해 직접 언급하지 않는다
  en:
    - Never directly mention the end of the world
"""

# speech_guide/example_lines가 없는 캐릭터
SAMPLE_CHARACTER_NO_SPEECH = """\
id: ae
priority: 99

name:
  kr: 아리엘라의 그림자
  en: The Shadow of Ariella

role:
  _display: inline
  kr: 아리엘라의 그림자
  en: The Shadow of Ariella

basic_info:
  _display: markdown
  kr: |
    그림자 캐릭터.
  en: |
    Shadow character.
"""


@pytest.fixture
def char_dir(tmp_path: Path):
    """임시 캐릭터 디렉토리를 생성하고 샘플 YAML을 배치."""
    d = tmp_path / "characters"
    d.mkdir()
    (d / "hn.yaml").write_text(SAMPLE_CHARACTER_YAML, encoding="utf-8")
    (d / "ae.yaml").write_text(SAMPLE_CHARACTER_NO_SPEECH, encoding="utf-8")
    (d / "actor_code.yaml").write_text("# skip\n", encoding="utf-8")
    return d


# ── CharacterLoader 테스트 ──────────────────────────────────────


class TestCharacterLoader:
    def test_load_all(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        chars = loader.load_all()
        # actor_code.yaml은 제외, hn + ae = 2
        assert len(chars) == 2
        assert "hn" in chars
        assert "ae" in chars

    def test_get_character(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        hn = loader.get("hn")
        assert hn is not None
        assert hn["id"] == "hn"
        assert hn["name"]["kr"] == "하니엘"
        assert hn["name"]["en"] == "Haniel"

    def test_get_nonexistent_returns_none(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        assert loader.get("zz") is None

    def test_extract_fields_kr(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        fields = loader.extract_fields("hn", lang="kr")
        assert fields is not None
        assert fields["name"] == "하니엘"
        assert fields["role"] == "천사, 펜릭스 부활 담당"
        assert "게으르고 의욕이 없다" in fields["personality"]
        assert "시니컬" in fields["speech_guide"]
        assert "너무 멀리 가지마" in fields["example_lines"]
        assert "안 죽고 돌아왔네" in fields["example_lines"]
        assert "세상의 종말" in fields["writing_guidelines"]

    def test_extract_fields_en(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        fields = loader.extract_fields("hn", lang="en")
        assert fields is not None
        assert fields["name"] == "Haniel"
        assert "Cynical" in fields["speech_guide"]

    def test_extract_fields_missing_character(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        assert loader.extract_fields("zz") is None

    def test_list_chat_ready(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader

        loader = CharacterLoader(char_dir)
        ready = loader.list_chat_ready()
        # ae에는 speech_guide/example_lines가 없으므로 hn만 포함
        assert len(ready) == 1
        item = ready[0]
        assert item["id"] == "hn"
        assert item["name"]["kr"] == "하니엘"
        assert item["role"]["kr"] == "천사, 펜릭스 부활 담당"
        assert "tagline" in item


# ── PromptBuilder 테스트 ─────────────────────────────────────


SAMPLE_TEMPLATE = """\
You are {name}, {role}.

## Personality
{personality}

## Speech Guide
{speech_guide}

## Example Lines
{example_lines}

## Writing Guidelines
{writing_guidelines}

## Basic Info
{basic_info}

## Relationships
{relationships}

## Situation
{situation}
"""


class TestPromptBuilder:
    def test_build_prompt_kr(self, char_dir: Path, tmp_path: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path)
        prompt = builder.build("hn", lang="kr")
        assert "하니엘" in prompt
        assert "천사, 펜릭스 부활 담당" in prompt
        assert "게으르고 의욕이 없다" in prompt
        assert "시니컬" in prompt

    def test_build_prompt_en(self, char_dir: Path, tmp_path: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path)
        prompt = builder.build("hn", lang="en")
        assert "Haniel" in prompt
        assert "Cynical" in prompt

    def test_build_with_situation(self, char_dir: Path, tmp_path: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path)
        prompt = builder.build("hn", lang="kr", situation="전투 직후 상황")
        assert "전투 직후 상황" in prompt

    def test_build_nonexistent_character(self, char_dir: Path, tmp_path: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path)
        assert builder.build("zz") is None

    def test_prompt_override_replaces_template(self, char_dir: Path, tmp_path: Path):
        """오버라이드 파일이 있으면 기본 템플릿 대신 사용."""
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        # 오버라이드 디렉토리에 hn.txt 생성
        override_dir = tmp_path / "overrides"
        override_dir.mkdir()
        override_content = "Custom prompt for {name}. Role: {role}. Situation: {situation}"
        (override_dir / "hn.txt").write_text(override_content, encoding="utf-8")

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path, prompt_override_dir=override_dir)
        prompt = builder.build("hn", lang="kr")

        assert "Custom prompt for 하니엘" in prompt
        assert "Role: 천사, 펜릭스 부활 담당" in prompt
        # 기본 템플릿의 내용은 없어야 함
        assert "## Personality" not in prompt

    def test_prompt_override_missing_falls_back(self, char_dir: Path, tmp_path: Path):
        """오버라이드 파일이 없으면 기본 템플릿 사용."""
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        # 오버라이드 디렉토리는 있지만 hn.txt는 없음
        override_dir = tmp_path / "overrides"
        override_dir.mkdir()

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path, prompt_override_dir=override_dir)
        prompt = builder.build("hn", lang="kr")

        # 기본 템플릿이 사용되어야 함
        assert "## Personality" in prompt
        assert "하니엘" in prompt

    def test_prompt_override_dir_not_exists(self, char_dir: Path, tmp_path: Path):
        """오버라이드 디렉토리 자체가 없으면 기본 템플릿 사용."""
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        override_dir = tmp_path / "nonexistent_overrides"
        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path, prompt_override_dir=override_dir)
        prompt = builder.build("hn", lang="kr")

        assert "## Personality" in prompt
        assert "하니엘" in prompt

    def test_prompt_override_none_uses_default(self, char_dir: Path, tmp_path: Path):
        """prompt_override_dir=None이면 기본 동작."""
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

        template_path = tmp_path / "npc_system.txt"
        template_path.write_text(SAMPLE_TEMPLATE, encoding="utf-8")

        loader = CharacterLoader(char_dir)
        builder = PromptBuilder(loader, template_path, prompt_override_dir=None)
        prompt = builder.build("hn", lang="kr")

        assert "## Personality" in prompt
        assert "하니엘" in prompt


# ── npc_list_characters 도구 테스트 ───────────────────────────


class TestNpcListCharacters:
    def test_returns_chat_ready_list(self, char_dir: Path):
        from seosoyoung.mcp.tools.npc_chat import CharacterLoader, npc_list_characters

        loader = CharacterLoader(char_dir)
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ):
            result = npc_list_characters()
        assert result["success"] is True
        chars = result["characters"]
        assert len(chars) == 1
        assert chars[0]["id"] == "hn"
        assert "name" in chars[0]
        assert "role" in chars[0]


# ── NpcSession 데이터 클래스 테스트 ─────────────────────────


class TestNpcSession:
    def test_session_defaults(self):
        from seosoyoung.mcp.tools.npc_chat import NpcSession

        session = NpcSession(
            session_id="test123",
            character_id="hn",
            system_prompt="You are Haniel.",
        )
        assert session.session_id == "test123"
        assert session.character_id == "hn"
        assert session.language == "kr"
        assert session.messages == []
        assert session.digest == ""
        assert session.created_at > 0

    def test_session_with_language(self):
        from seosoyoung.mcp.tools.npc_chat import NpcSession

        session = NpcSession(
            session_id="test456",
            character_id="hn",
            system_prompt="You are Haniel.",
            language="en",
        )
        assert session.language == "en"


# ── Claude API 연동 테스트 ──────────────────────────────────


class TestClaudeApi:
    def test_get_api_key_from_env(self, monkeypatch):
        from seosoyoung.mcp.tools.npc_chat import _get_api_key

        monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-key-123")
        assert _get_api_key() == "test-key-123"

    def test_get_api_key_missing_raises(self, monkeypatch):
        from seosoyoung.mcp.tools.npc_chat import _get_api_key

        monkeypatch.delenv("NPC_CLAUDE_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="NPC_CLAUDE_API_KEY"):
            _get_api_key()

    def test_call_claude(self, monkeypatch):
        from seosoyoung.mcp.tools.npc_chat import _call_claude

        monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-key")
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Hello, mortal.")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("seosoyoung.mcp.tools.npc_chat._get_client", return_value=mock_client):
            result = _call_claude("system", [{"role": "user", "content": "hi"}])

        assert result == "Hello, mortal."
        mock_client.messages.create.assert_called_once_with(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system="system",
            messages=[{"role": "user", "content": "hi"}],
        )


# ── 다이제스트 테스트 ──────────────────────────────────────


class TestDigest:
    def test_build_digest(self, monkeypatch):
        from seosoyoung.mcp.tools.npc_chat import _build_digest

        monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-key")
        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Summary: user greeted NPC.",
        ):
            digest = _build_digest("sys", [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello."},
            ])
        assert "Summary" in digest

    def test_maybe_compress_under_threshold(self):
        from seosoyoung.mcp.tools.npc_chat import NpcSession, _maybe_compress

        session = NpcSession(
            session_id="s1", character_id="hn", system_prompt="sys"
        )
        # 10턴 (threshold=20 이하)
        for i in range(10):
            session.messages.append({"role": "user", "content": f"msg-{i}"})
        _maybe_compress(session)
        assert len(session.messages) == 10
        assert session.digest == ""

    def test_maybe_compress_over_threshold(self, monkeypatch):
        from seosoyoung.mcp.tools.npc_chat import (
            DIGEST_KEEP_RECENT,
            DIGEST_THRESHOLD,
            NpcSession,
            _maybe_compress,
        )

        monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-key")
        session = NpcSession(
            session_id="s2", character_id="hn", system_prompt="sys"
        )
        # threshold + 5 메시지
        for i in range(DIGEST_THRESHOLD + 5):
            role = "user" if i % 2 == 0 else "assistant"
            session.messages.append({"role": role, "content": f"msg-{i}"})

        with patch(
            "seosoyoung.mcp.tools.npc_chat._build_digest",
            return_value="Digest of old messages.",
        ):
            _maybe_compress(session)

        assert len(session.messages) == DIGEST_KEEP_RECENT
        assert session.digest == "Digest of old messages."

    def test_maybe_compress_appends_existing_digest(self, monkeypatch):
        from seosoyoung.mcp.tools.npc_chat import (
            DIGEST_KEEP_RECENT,
            DIGEST_THRESHOLD,
            NpcSession,
            _maybe_compress,
        )

        monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-key")
        session = NpcSession(
            session_id="s3", character_id="hn", system_prompt="sys",
        )
        session.digest = "Old digest."
        for i in range(DIGEST_THRESHOLD + 5):
            role = "user" if i % 2 == 0 else "assistant"
            session.messages.append({"role": role, "content": f"msg-{i}"})

        with patch(
            "seosoyoung.mcp.tools.npc_chat._build_digest",
            return_value="New digest.",
        ):
            _maybe_compress(session)

        assert "Old digest." in session.digest
        assert "New digest." in session.digest
        assert len(session.messages) == DIGEST_KEEP_RECENT


# ── API 메시지 빌드 테스트 ─────────────────────────────────


class TestBuildApiMessages:
    def test_without_digest(self):
        from seosoyoung.mcp.tools.npc_chat import NpcSession, _build_api_messages

        session = NpcSession(
            session_id="s1", character_id="hn", system_prompt="sys"
        )
        session.messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        msgs = _build_api_messages(session)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "hi"

    def test_with_digest(self):
        from seosoyoung.mcp.tools.npc_chat import NpcSession, _build_api_messages

        session = NpcSession(
            session_id="s1", character_id="hn", system_prompt="sys"
        )
        session.digest = "Previously, user asked about weather."
        session.messages = [
            {"role": "user", "content": "What about tomorrow?"},
        ]
        msgs = _build_api_messages(session)
        # digest (user) + ack (assistant) + actual message = 3
        assert len(msgs) == 3
        assert "Previous conversation summary" in msgs[0]["content"]
        assert msgs[1]["role"] == "assistant"


# ── MCP 도구 함수 테스트 (Phase 2) ─────────────────────────


@pytest.fixture
def mock_claude_env(monkeypatch):
    """Claude API를 mock하는 fixture."""
    monkeypatch.setenv("NPC_CLAUDE_API_KEY", "test-key")
    return monkeypatch


@pytest.fixture
def template_dir(tmp_path: Path):
    """프롬프트 템플릿 디렉토리를 생성."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "npc_system.txt").write_text(SAMPLE_TEMPLATE, encoding="utf-8")
    return prompts_dir


@pytest.fixture
def setup_npc_env(char_dir, template_dir, mock_claude_env):
    """캐릭터 로더와 세션 딕셔너리를 초기화하는 fixture."""
    from seosoyoung.mcp.tools.npc_chat import CharacterLoader, PromptBuilder

    loader = CharacterLoader(char_dir)
    builder = PromptBuilder(loader, template_dir / "npc_system.txt")

    # 세션 딕셔너리 초기화
    import seosoyoung.mcp.tools.npc_chat as npc_mod
    npc_mod._sessions.clear()

    return loader, builder


class TestNpcOpenSession:
    def test_open_session_success(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session, _sessions

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="흐음~ 뭔 일이야.",
        ):
            result = npc_open_session("hn")

        assert result["success"] is True
        assert "session_id" in result
        assert result["character_id"] == "hn"
        assert result["language"] == "kr"
        assert result["message"] == "흐음~ 뭔 일이야."
        # 세션이 저장되었는지 확인
        assert result["session_id"] in _sessions

    def test_open_session_with_situation(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="전투 끝났네? 수고했어.",
        ) as mock_call:
            result = npc_open_session("hn", situation="전투 직후")

        assert result["success"] is True
        # _call_claude에 전달된 메시지에 situation이 포함되어 있는지 확인
        call_args = mock_call.call_args
        messages = call_args[0][1]
        assert "전투 직후" in messages[0]["content"]

    def test_open_session_invalid_character(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ):
            result = npc_open_session("nonexistent")

        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]

    def test_open_session_en(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Oh, you're here.",
        ):
            result = npc_open_session("hn", language="en")

        assert result["success"] is True
        assert result["language"] == "en"


class TestNpcTalk:
    def _create_session(self, setup_npc_env):
        """테스트용 세션을 생성하고 session_id를 반환."""
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Opening line.",
        ):
            result = npc_open_session("hn")
        return result["session_id"]

    def test_talk_success(self, setup_npc_env):
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_talk

        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="뭐, 그래.",
        ):
            result = npc_talk(session_id, "안녕!")

        assert result["success"] is True
        assert result["message"] == "뭐, 그래."
        assert result["turn_count"] == 4  # opening(user,assistant) + talk(user,assistant)

    def test_talk_invalid_session(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_talk

        result = npc_talk("nonexistent", "안녕!")
        assert result["success"] is False
        assert "찾을 수 없습니다" in result["error"]

    def test_talk_multiple_turns(self, setup_npc_env):
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_talk

        replies = ["Reply 1.", "Reply 2.", "Reply 3."]
        for i, expected_reply in enumerate(replies):
            with patch(
                "seosoyoung.mcp.tools.npc_chat._call_claude",
                return_value=expected_reply,
            ):
                result = npc_talk(session_id, f"Message {i}")
            assert result["success"] is True
            assert result["message"] == expected_reply


class TestNpcSetSituation:
    def _create_session(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Opening.",
        ):
            result = npc_open_session("hn")
        return result["session_id"]

    def test_set_situation_success(self, setup_npc_env):
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_set_situation, _sessions

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="어, 갑자기 비가...",
        ):
            result = npc_set_situation(session_id, "비가 내리기 시작함")

        assert result["success"] is True
        assert result["situation"] == "비가 내리기 시작함"
        assert result["message"] == "어, 갑자기 비가..."
        # 시스템 프롬프트에 새 상황이 반영되었는지 확인
        session = _sessions[session_id]
        assert "비가 내리기 시작함" in session.system_prompt

    def test_set_situation_invalid_session(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_set_situation

        result = npc_set_situation("nonexistent", "new situation")
        assert result["success"] is False


class TestNpcCloseSession:
    def _create_session(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Opening.",
        ):
            result = npc_open_session("hn")
        return result["session_id"]

    def test_close_session_success(self, setup_npc_env):
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_close_session, _sessions

        result = npc_close_session(session_id)
        assert result["success"] is True
        assert result["session_id"] == session_id
        assert result["character_id"] == "hn"
        assert result["turn_count"] == 2  # opening pair
        assert len(result["history"]) == 2
        # 세션이 삭제되었는지 확인
        assert session_id not in _sessions

    def test_close_session_invalid(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_close_session

        result = npc_close_session("nonexistent")
        assert result["success"] is False

    def test_close_then_talk_fails(self, setup_npc_env):
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_close_session, npc_talk

        npc_close_session(session_id)
        result = npc_talk(session_id, "Hello?")
        assert result["success"] is False


class TestNpcGetHistory:
    def _create_session(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_open_session

        loader, _ = setup_npc_env
        with patch(
            "seosoyoung.mcp.tools.npc_chat._get_loader", return_value=loader
        ), patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Opening.",
        ):
            result = npc_open_session("hn")
        return result["session_id"]

    def test_get_history(self, setup_npc_env):
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_get_history

        result = npc_get_history(session_id)
        assert result["success"] is True
        assert result["turn_count"] == 2
        assert result["has_digest"] is False
        assert len(result["history"]) == 2

    def test_get_history_preserves_session(self, setup_npc_env):
        """get_history는 세션을 유지해야 함 (close와 다름)."""
        session_id = self._create_session(setup_npc_env)
        from seosoyoung.mcp.tools.npc_chat import npc_get_history, npc_talk

        npc_get_history(session_id)
        # 세션이 유지되어 추가 대화 가능
        with patch(
            "seosoyoung.mcp.tools.npc_chat._call_claude",
            return_value="Still here.",
        ):
            result = npc_talk(session_id, "Are you still there?")
        assert result["success"] is True

    def test_get_history_invalid(self, setup_npc_env):
        from seosoyoung.mcp.tools.npc_chat import npc_get_history

        result = npc_get_history("nonexistent")
        assert result["success"] is False
