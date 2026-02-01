"""도구 정의 로더 테스트 (TDD RED 단계)"""

import pytest
from pathlib import Path
from seosoyoung.routing.loader import (
    ToolDefinition,
    AgentDefinition,
    SkillDefinition,
    ToolLoader,
    parse_frontmatter,
)


class TestParseFrontmatter:
    """Frontmatter 파싱 테스트"""

    def test_parse_valid_frontmatter(self):
        """유효한 frontmatter 파싱"""
        content = """---
name: test-agent
description: 테스트 에이전트입니다.
---

# 본문 내용
이것은 본문입니다.
"""
        frontmatter, body = parse_frontmatter(content)
        assert frontmatter["name"] == "test-agent"
        assert frontmatter["description"] == "테스트 에이전트입니다."
        assert "# 본문 내용" in body
        assert "이것은 본문입니다." in body

    def test_parse_multiline_description(self):
        """멀티라인 description 파싱"""
        content = """---
name: lore
description: |
  사용자가 캐릭터나 배경 설정에 대해서 문의하거나,
  수정을 요청할 때 사용하는 에이전트입니다.
---

# 작업 지침
"""
        frontmatter, body = parse_frontmatter(content)
        assert frontmatter["name"] == "lore"
        assert "캐릭터나 배경 설정" in frontmatter["description"]
        assert "# 작업 지침" in body

    def test_parse_no_frontmatter(self):
        """frontmatter가 없는 파일"""
        content = """# 제목만 있는 파일

본문 내용입니다.
"""
        frontmatter, body = parse_frontmatter(content)
        assert frontmatter == {}
        assert "# 제목만 있는 파일" in body

    def test_parse_empty_frontmatter(self):
        """빈 frontmatter"""
        content = """---
---

# 본문
"""
        frontmatter, body = parse_frontmatter(content)
        assert frontmatter == {}
        assert "# 본문" in body


class TestToolDefinition:
    """ToolDefinition 데이터 클래스 테스트"""

    def test_create_tool_definition(self):
        """ToolDefinition 생성"""
        tool = ToolDefinition(
            name="test-tool",
            description="테스트 도구입니다.",
            tool_type="agent",
            file_path=Path("/path/to/tool.md"),
        )
        assert tool.name == "test-tool"
        assert tool.description == "테스트 도구입니다."
        assert tool.tool_type == "agent"

    def test_tool_definition_summary(self):
        """요약본 생성 - description만 포함"""
        tool = ToolDefinition(
            name="lore",
            description="캐릭터나 배경 설정에 대해 문의하거나 수정을 요청할 때 사용합니다.",
            tool_type="agent",
            file_path=Path("/path/to/lore.md"),
            body="# 작업 지침\n\n매우 긴 본문 내용...",
        )
        summary = tool.to_summary()
        assert summary["name"] == "lore"
        assert summary["description"] == tool.description
        assert summary["type"] == "agent"
        assert "body" not in summary  # 본문은 요약에 포함되지 않음


class TestAgentDefinition:
    """AgentDefinition 테스트"""

    def test_create_agent_definition(self):
        """AgentDefinition 생성"""
        agent = AgentDefinition(
            name="lore",
            description="로어 에이전트입니다.",
            file_path=Path(".claude/agents/lore.md"),
        )
        assert agent.tool_type == "agent"
        assert agent.name == "lore"


class TestSkillDefinition:
    """SkillDefinition 테스트"""

    def test_create_skill_definition(self):
        """SkillDefinition 생성"""
        skill = SkillDefinition(
            name="search-glossary",
            description="용어집 검색 스킬",
            file_path=Path(".claude/skills/lore-search-glossary/SKILL.md"),
            allowed_tools=["Read", "Glob", "Grep"],
        )
        assert skill.tool_type == "skill"
        assert skill.name == "search-glossary"
        assert "Read" in skill.allowed_tools

    def test_skill_summary_includes_allowed_tools(self):
        """스킬 요약에 allowed_tools 포함"""
        skill = SkillDefinition(
            name="search-glossary",
            description="용어집 검색",
            file_path=Path(".claude/skills/lore-search-glossary/SKILL.md"),
            allowed_tools=["Read", "Glob"],
        )
        summary = skill.to_summary()
        assert "allowed_tools" in summary
        assert summary["allowed_tools"] == ["Read", "Glob"]


class TestToolLoader:
    """ToolLoader 테스트"""

    @pytest.fixture
    def workspace_path(self, tmp_path):
        """임시 워크스페이스 생성"""
        # .claude/agents 디렉토리 생성
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)

        # 에이전트 파일 생성
        (agents_dir / "lore.md").write_text(
            """---
name: lore
description: 로어 관련 작업을 처리하는 에이전트입니다.
---

# 작업 지침
캐릭터와 설정 정보를 관리합니다.
""",
            encoding="utf-8",
        )

        (agents_dir / "slackbot-dev.md").write_text(
            """---
name: slackbot-dev
description: 슬랙봇 개발 관련 작업을 처리합니다.
---

# 개발 지침
""",
            encoding="utf-8",
        )

        # .claude/skills 디렉토리 생성
        skill_dir = tmp_path / ".claude" / "skills" / "lore-search-glossary"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            """---
name: search-glossary
description: 캐릭터나 장소 정보를 검색합니다.
allowed-tools: Read, Glob, Grep
---

# 용어집 검색
검색 절차를 설명합니다.
""",
            encoding="utf-8",
        )

        return tmp_path

    def test_load_agents(self, workspace_path):
        """에이전트 로드"""
        loader = ToolLoader(workspace_path)
        agents = loader.load_agents()

        assert len(agents) == 2
        names = [a.name for a in agents]
        assert "lore" in names
        assert "slackbot-dev" in names

    def test_load_skills(self, workspace_path):
        """스킬 로드"""
        loader = ToolLoader(workspace_path)
        skills = loader.load_skills()

        assert len(skills) == 1
        assert skills[0].name == "search-glossary"
        assert skills[0].allowed_tools == ["Read", "Glob", "Grep"]

    def test_load_all_tools(self, workspace_path):
        """모든 도구 로드"""
        loader = ToolLoader(workspace_path)
        tools = loader.load_all()

        assert len(tools) == 3
        agent_count = sum(1 for t in tools if t.tool_type == "agent")
        skill_count = sum(1 for t in tools if t.tool_type == "skill")
        assert agent_count == 2
        assert skill_count == 1

    def test_generate_summaries(self, workspace_path):
        """요약본 생성"""
        loader = ToolLoader(workspace_path)
        tools = loader.load_all()
        summaries = loader.generate_summaries(tools)

        assert len(summaries) == 3
        for summary in summaries:
            assert "name" in summary
            assert "description" in summary
            assert "type" in summary
            # 본문은 포함되지 않아야 함
            assert "body" not in summary

    def test_empty_workspace(self, tmp_path):
        """빈 워크스페이스"""
        loader = ToolLoader(tmp_path)
        tools = loader.load_all()
        assert tools == []

    def test_malformed_frontmatter_skipped(self, workspace_path):
        """잘못된 frontmatter는 건너뜀"""
        agents_dir = workspace_path / ".claude" / "agents"
        (agents_dir / "broken.md").write_text(
            """---
name: broken
description: [잘못된 YAML
---
""",
            encoding="utf-8",
        )

        loader = ToolLoader(workspace_path)
        agents = loader.load_agents()

        # 잘못된 파일은 건너뛰고 유효한 2개만 로드
        assert len(agents) == 2


class TestToolLoaderWithRealFiles:
    """실제 파일로 테스트 (통합 테스트)"""

    @pytest.fixture
    def real_workspace(self):
        """실제 워크스페이스 경로"""
        workspace = Path(__file__).parent.parent.parent.parent.parent
        if (workspace / ".claude" / "agents").exists():
            return workspace
        pytest.skip("실제 워크스페이스를 찾을 수 없음")

    def test_load_real_agents(self, real_workspace):
        """실제 에이전트 파일 로드"""
        loader = ToolLoader(real_workspace)
        agents = loader.load_agents()

        assert len(agents) > 0
        # lore 에이전트가 있어야 함
        names = [a.name for a in agents]
        assert "lore" in names

    def test_load_real_skills(self, real_workspace):
        """실제 스킬 파일 로드"""
        loader = ToolLoader(real_workspace)
        skills = loader.load_skills()

        assert len(skills) > 0
