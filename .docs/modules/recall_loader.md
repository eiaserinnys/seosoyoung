# recall/loader.py

> 경로: `seosoyoung/recall/loader.py`

## 개요

도구 정의 로더

.claude/agents/*.md와 .claude/skills/*/SKILL.md 파일을 파싱하여
도구 정의를 로드하는 모듈.

## 클래스

### `ToolDefinition`
- 위치: 줄 51
- 설명: 도구 정의 기본 클래스

#### 메서드

- `to_summary(self)` (줄 60): 토큰 효율적인 요약본 생성.

### `AgentDefinition` (ToolDefinition)
- 위치: 줄 73
- 설명: 에이전트 정의

#### 메서드

- `__init__(self, name, description, file_path, body)` (줄 78): 

### `SkillDefinition` (ToolDefinition)
- 위치: 줄 95
- 설명: 스킬 정의

#### 메서드

- `__init__(self, name, description, file_path, body, allowed_tools)` (줄 101): 
- `to_summary(self)` (줄 118): 스킬 요약본 - allowed_tools 포함

### `ToolLoader`
- 위치: 줄 125
- 설명: 도구 정의 로더

#### 메서드

- `__init__(self, workspace_path)` (줄 128): Args:
- `load_agents(self)` (줄 137): 에이전트 정의 로드.
- `load_skills(self)` (줄 170): 스킬 정의 로드.
- `load_all(self)` (줄 222): 모든 도구 정의 로드.
- `generate_summaries(self, tools)` (줄 233): 도구 목록의 요약본 생성.

## 함수

### `parse_frontmatter(content)`
- 위치: 줄 19
- 설명: YAML frontmatter와 본문을 분리하여 파싱.

Args:
    content: 마크다운 파일 내용

Returns:
    (frontmatter dict, body string) 튜플
