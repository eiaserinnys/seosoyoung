"""도구 정의 로더

.claude/agents/*.md와 .claude/skills/*/SKILL.md 파일을 파싱하여
도구 정의를 로드하는 모듈.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import logging
import re

import yaml


logger = logging.getLogger(__name__)


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """YAML frontmatter와 본문을 분리하여 파싱.

    Args:
        content: 마크다운 파일 내용

    Returns:
        (frontmatter dict, body string) 튜플
    """
    # frontmatter 패턴: --- 로 시작하고 --- 로 끝남
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        return {}, content

    yaml_content = match.group(1).strip()
    body = match.group(2).strip()

    if not yaml_content:
        return {}, body

    try:
        frontmatter = yaml.safe_load(yaml_content) or {}
    except yaml.YAMLError as e:
        logger.warning(f"YAML 파싱 실패: {e}")
        return {}, content

    return frontmatter, body


@dataclass
class ToolDefinition:
    """도구 정의 기본 클래스"""

    name: str
    description: str
    tool_type: str
    file_path: Path
    body: str = ""

    def to_summary(self) -> dict[str, Any]:
        """토큰 효율적인 요약본 생성.

        본문을 제외하고 name, description, type만 포함.
        """
        return {
            "name": self.name,
            "description": self.description,
            "type": self.tool_type,
        }


@dataclass
class AgentDefinition(ToolDefinition):
    """에이전트 정의"""

    tool_type: str = field(default="agent", init=False)

    def __init__(
        self,
        name: str,
        description: str,
        file_path: Path,
        body: str = "",
    ):
        super().__init__(
            name=name,
            description=description,
            tool_type="agent",
            file_path=file_path,
            body=body,
        )


@dataclass
class SkillDefinition(ToolDefinition):
    """스킬 정의"""

    tool_type: str = field(default="skill", init=False)
    allowed_tools: list[str] = field(default_factory=list)

    def __init__(
        self,
        name: str,
        description: str,
        file_path: Path,
        body: str = "",
        allowed_tools: list[str] | None = None,
    ):
        super().__init__(
            name=name,
            description=description,
            tool_type="skill",
            file_path=file_path,
            body=body,
        )
        self.allowed_tools = allowed_tools or []

    def to_summary(self) -> dict[str, Any]:
        """스킬 요약본 - allowed_tools 포함"""
        summary = super().to_summary()
        summary["allowed_tools"] = self.allowed_tools
        return summary


class ToolLoader:
    """도구 정의 로더"""

    def __init__(self, workspace_path: Path):
        """
        Args:
            workspace_path: 워크스페이스 루트 경로
        """
        self.workspace_path = Path(workspace_path)
        self.agents_dir = self.workspace_path / ".claude" / "agents"
        self.skills_dir = self.workspace_path / ".claude" / "skills"

    def load_agents(self) -> list[AgentDefinition]:
        """에이전트 정의 로드.

        Returns:
            AgentDefinition 리스트
        """
        agents = []

        if not self.agents_dir.exists():
            return agents

        for agent_file in self.agents_dir.glob("*.md"):
            try:
                content = agent_file.read_text(encoding="utf-8")
                frontmatter, body = parse_frontmatter(content)

                if not frontmatter.get("name"):
                    logger.warning(f"에이전트 파일에 name이 없음: {agent_file}")
                    continue

                agent = AgentDefinition(
                    name=frontmatter["name"],
                    description=frontmatter.get("description", ""),
                    file_path=agent_file,
                    body=body,
                )
                agents.append(agent)
            except Exception as e:
                logger.warning(f"에이전트 파일 로드 실패 {agent_file}: {e}")
                continue

        return agents

    def load_skills(self) -> list[SkillDefinition]:
        """스킬 정의 로드.

        Returns:
            SkillDefinition 리스트
        """
        skills = []

        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                content = skill_file.read_text(encoding="utf-8")
                frontmatter, body = parse_frontmatter(content)

                if not frontmatter.get("name"):
                    logger.warning(f"스킬 파일에 name이 없음: {skill_file}")
                    continue

                # allowed-tools 파싱 (쉼표로 구분된 문자열)
                allowed_tools_raw = frontmatter.get("allowed-tools", "")
                if isinstance(allowed_tools_raw, str):
                    allowed_tools = [
                        t.strip()
                        for t in allowed_tools_raw.split(",")
                        if t.strip()
                    ]
                else:
                    allowed_tools = allowed_tools_raw or []

                skill = SkillDefinition(
                    name=frontmatter["name"],
                    description=frontmatter.get("description", ""),
                    file_path=skill_file,
                    body=body,
                    allowed_tools=allowed_tools,
                )
                skills.append(skill)
            except Exception as e:
                logger.warning(f"스킬 파일 로드 실패 {skill_file}: {e}")
                continue

        return skills

    def load_all(self) -> list[ToolDefinition]:
        """모든 도구 정의 로드.

        Returns:
            ToolDefinition 리스트 (에이전트 + 스킬)
        """
        tools: list[ToolDefinition] = []
        tools.extend(self.load_agents())
        tools.extend(self.load_skills())
        return tools

    def generate_summaries(
        self, tools: list[ToolDefinition]
    ) -> list[dict[str, Any]]:
        """도구 목록의 요약본 생성.

        Args:
            tools: ToolDefinition 리스트

        Returns:
            요약 딕셔너리 리스트
        """
        return [tool.to_summary() for tool in tools]
