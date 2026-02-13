"""NPC 대화 모듈 단위 테스트 (캐릭터 로더, 프롬프트 빌더, npc_list_characters)"""

from pathlib import Path
from unittest.mock import patch

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
