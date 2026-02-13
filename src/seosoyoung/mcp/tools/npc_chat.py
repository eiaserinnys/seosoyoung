"""NPC 대화 모듈: 캐릭터 로더, 프롬프트 빌더, 세션 관리, Claude API 연동."""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


# ── 기본 경로 설정 ──────────────────────────────────────────

_DEFAULT_CHARACTERS_DIR = (
    Path(__file__).resolve().parents[5] / "eb_lore" / "content" / "characters"
)
_DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "npc_system.txt"
_DEFAULT_PROMPT_OVERRIDE_DIR = Path(__file__).resolve().parents[5] / ".local" / "prompts"

# 캐릭터 파일에서 제외할 파일명 (확장자 제외)
_SKIP_FILES = {"actor_code"}


# ── CharacterLoader ─────────────────────────────────────────


class CharacterLoader:
    """eb_lore 캐릭터 YAML 파일을 로드하고 필드를 추출한다."""

    def __init__(self, characters_dir: Optional[Path] = None):
        self._dir = characters_dir or _DEFAULT_CHARACTERS_DIR
        self._cache: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load_all(self) -> dict[str, dict[str, Any]]:
        """모든 캐릭터 YAML을 로드하여 {id: data} 딕셔너리로 반환."""
        if self._loaded:
            return self._cache
        for path in sorted(self._dir.glob("*.yaml")):
            if path.stem in _SKIP_FILES:
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if data and isinstance(data, dict) and "id" in data:
                self._cache[data["id"]] = data
        self._loaded = True
        return self._cache

    def get(self, character_id: str) -> Optional[dict[str, Any]]:
        """캐릭터 ID로 원본 데이터를 반환. 없으면 None."""
        self.load_all()
        return self._cache.get(character_id)

    def extract_fields(
        self, character_id: str, lang: str = "kr"
    ) -> Optional[dict[str, Any]]:
        """프롬프트 빌더에 필요한 필드를 언어별로 추출."""
        data = self.get(character_id)
        if data is None:
            return None

        def _get_localized(field: dict | Any) -> str:
            """_display 메타데이터를 가진 필드에서 해당 언어 값을 꺼낸다."""
            if isinstance(field, dict):
                if lang in field:
                    val = field[lang]
                    if isinstance(val, list):
                        return "\n".join(f"- {item}" for item in val)
                    return str(val).strip()
            return ""

        def _get_relationships() -> str:
            """관계 테이블을 텍스트로 변환."""
            rel = data.get("relationships")
            if not rel or "items" not in rel:
                return ""
            lines = []
            for item in rel["items"]:
                char_name = item.get("character", {}).get(lang, "")
                relation = item.get("relation", {}).get(lang, "")
                if char_name and relation:
                    lines.append(f"- {char_name}: {relation}")
            return "\n".join(lines)

        return {
            "name": _get_localized(data.get("name", {})),
            "role": _get_localized(data.get("role", {})),
            "basic_info": _get_localized(data.get("basic_info", {})),
            "personality": _get_localized(data.get("personality", {})),
            "relationships": _get_relationships(),
            "speech_guide": _get_localized(data.get("speech_guide", {})),
            "example_lines": _get_localized(data.get("example_lines", {})),
            "writing_guidelines": _get_localized(
                data.get("writing_guidelines", {})
            ),
        }

    def list_chat_ready(self) -> list[dict[str, Any]]:
        """대화 가능한(speech_guide + example_lines 보유) 캐릭터 목록 반환."""
        self.load_all()
        result = []
        for cid, data in self._cache.items():
            speech = data.get("speech_guide")
            examples = data.get("example_lines")
            if not speech or not examples:
                continue
            entry: dict[str, Any] = {
                "id": cid,
                "name": data.get("name", {}),
                "role": data.get("role", {}),
            }
            tagline = data.get("tagline")
            if tagline:
                entry["tagline"] = tagline
            result.append(entry)
        # priority 기준 정렬
        result.sort(key=lambda x: self._cache[x["id"]].get("priority", 999))
        return result


# ── PromptBuilder ───────────────────────────────────────────


class PromptBuilder:
    """캐릭터 데이터를 프롬프트 템플릿에 채워 시스템 프롬프트를 생성한다."""

    def __init__(
        self,
        loader: CharacterLoader,
        template_path: Optional[Path] = None,
        prompt_override_dir: Optional[Path] = None,
    ):
        self._loader = loader
        self._template_path = template_path or _DEFAULT_TEMPLATE_PATH
        self._prompt_override_dir = prompt_override_dir
        self._template: Optional[str] = None

    def _load_template(self, character_id: str) -> str:
        """캐릭터별 오버라이드 파일이 있으면 우선 사용, 없으면 기본 템플릿."""
        if self._prompt_override_dir is not None:
            override_path = self._prompt_override_dir / f"{character_id}.txt"
            if override_path.is_file():
                return override_path.read_text(encoding="utf-8")
        if self._template is None:
            self._template = self._template_path.read_text(encoding="utf-8")
        return self._template

    def build(
        self,
        character_id: str,
        lang: str = "kr",
        situation: str = "",
    ) -> Optional[str]:
        """캐릭터 ID와 언어로 시스템 프롬프트를 생성. 캐릭터가 없으면 None."""
        fields = self._loader.extract_fields(character_id, lang=lang)
        if fields is None:
            return None
        template = self._load_template(character_id)
        return template.format(
            **fields,
            situation=situation,
        )


# ── 싱글턴 로더 접근 ───────────────────────────────────────


_loader_instance: Optional[CharacterLoader] = None


def _get_loader() -> CharacterLoader:
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = CharacterLoader()
    return _loader_instance


# ── MCP 도구 함수 ──────────────────────────────────────────


def npc_list_characters() -> dict[str, Any]:
    """대화 가능한 NPC 캐릭터 목록을 반환한다."""
    loader = _get_loader()
    characters = loader.list_chat_ready()
    return {
        "success": True,
        "characters": characters,
        "count": len(characters),
    }


# ── NpcSession 데이터 클래스 ──────────────────────────────


@dataclass
class NpcSession:
    """NPC 대화 세션. 세션별 대화 이력과 설정을 보관한다."""

    session_id: str
    character_id: str
    system_prompt: str
    language: str = "kr"
    messages: list[dict[str, str]] = field(default_factory=list)
    digest: str = ""
    created_at: float = field(default_factory=time.time)


# ── Claude API 클라이언트 ─────────────────────────────────

# 다이제스트 임계치 (이 턴 수를 초과하면 오래된 대화를 다이제스트로 압축)
DIGEST_THRESHOLD = 20
# 다이제스트 시 보존할 최근 메시지 수
DIGEST_KEEP_RECENT = 6


def _get_api_key() -> str:
    """NPC_CLAUDE_API_KEY 환경변수에서 API 키를 가져온다."""
    key = os.environ.get("NPC_CLAUDE_API_KEY", "")
    if not key:
        raise RuntimeError("NPC_CLAUDE_API_KEY 환경변수가 설정되지 않았습니다.")
    return key


def _get_client():
    """Anthropic 클라이언트를 생성한다 (lazy import)."""
    import anthropic

    return anthropic.Anthropic(api_key=_get_api_key())


def _call_claude(
    system_prompt: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1024,
) -> str:
    """Claude API를 호출하여 assistant 응답 텍스트를 반환한다."""
    client = _get_client()
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text


def _build_digest(system_prompt: str, messages: list[dict[str, str]]) -> str:
    """메시지 목록을 요약하여 다이제스트 텍스트를 생성한다."""
    digest_prompt = (
        "You are a conversation summarizer. "
        "Summarize the following conversation between a user and an NPC character. "
        "Keep character-relevant details, emotional tone, and key topics. "
        "Write the summary in the same language as the conversation. "
        "Be concise (under 200 words)."
    )
    # 요약 대상 메시지를 하나의 user 메시지로 변환
    lines = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "NPC"
        lines.append(f"{role_label}: {msg['content']}")
    summary_request = [
        {"role": "user", "content": "\n".join(lines)},
    ]
    return _call_claude(digest_prompt, summary_request, max_tokens=512)


# ── 세션 매니저 ──────────────────────────────────────────

_sessions: dict[str, NpcSession] = {}


def _get_session(session_id: str) -> NpcSession:
    """세션 ID로 세션을 반환한다. 없으면 KeyError."""
    if session_id not in _sessions:
        raise KeyError(f"세션을 찾을 수 없습니다: {session_id}")
    return _sessions[session_id]


def _maybe_compress(session: NpcSession) -> None:
    """대화 이력이 임계치를 넘으면 다이제스트로 압축한다."""
    turn_count = len(session.messages)
    if turn_count <= DIGEST_THRESHOLD:
        return
    # 오래된 메시지를 다이제스트로 변환
    old_messages = session.messages[: turn_count - DIGEST_KEEP_RECENT]
    new_digest = _build_digest(session.system_prompt, old_messages)
    # 기존 다이제스트가 있으면 합침
    if session.digest:
        session.digest = session.digest + "\n\n" + new_digest
    else:
        session.digest = new_digest
    # 최근 메시지만 보존
    session.messages = session.messages[turn_count - DIGEST_KEEP_RECENT :]


def _build_api_messages(session: NpcSession) -> list[dict[str, str]]:
    """세션의 다이제스트 + 메시지를 Claude API 호출용 메시지 리스트로 변환한다."""
    msgs: list[dict[str, str]] = []
    if session.digest:
        msgs.append({
            "role": "user",
            "content": f"[Previous conversation summary]\n{session.digest}",
        })
        msgs.append({
            "role": "assistant",
            "content": "(Understood. I'll continue the conversation based on this context.)",
        })
    msgs.extend(session.messages)
    return msgs


# ── MCP 도구 함수 (Phase 2) ──────────────────────────────


def npc_open_session(
    character_id: str,
    situation: str = "",
    language: str = "kr",
) -> dict[str, Any]:
    """NPC 대화 세션을 열고 NPC의 첫 반응을 반환한다."""
    loader = _get_loader()
    builder = PromptBuilder(loader, prompt_override_dir=_DEFAULT_PROMPT_OVERRIDE_DIR)
    system_prompt = builder.build(character_id, lang=language, situation=situation)
    if system_prompt is None:
        return {"success": False, "error": f"캐릭터를 찾을 수 없습니다: {character_id}"}

    session_id = uuid.uuid4().hex[:12]
    session = NpcSession(
        session_id=session_id,
        character_id=character_id,
        system_prompt=system_prompt,
        language=language,
    )

    # 상황 설명이 있으면 초기 컨텍스트로 사용
    opening_prompt = "Start the conversation. Greet the user or react to the current situation naturally, in character."
    if situation:
        opening_prompt = (
            f"The current situation is: {situation}\n"
            "React to this situation naturally, in character. Start the conversation."
        )
    session.messages.append({"role": "user", "content": opening_prompt})

    reply = _call_claude(system_prompt, session.messages)
    session.messages.append({"role": "assistant", "content": reply})

    _sessions[session_id] = session
    return {
        "success": True,
        "session_id": session_id,
        "character_id": character_id,
        "language": language,
        "message": reply,
    }


def npc_talk(session_id: str, message: str) -> dict[str, Any]:
    """NPC에게 말하기. 사용자 메시지를 보내고 NPC 응답을 받는다."""
    try:
        session = _get_session(session_id)
    except KeyError as e:
        return {"success": False, "error": str(e)}

    session.messages.append({"role": "user", "content": message})

    # 압축 후 API 호출
    _maybe_compress(session)
    api_messages = _build_api_messages(session)
    reply = _call_claude(session.system_prompt, api_messages)
    session.messages.append({"role": "assistant", "content": reply})

    return {
        "success": True,
        "session_id": session_id,
        "message": reply,
        "turn_count": len(session.messages),
    }


def npc_set_situation(session_id: str, situation: str) -> dict[str, Any]:
    """대화 중 상황을 변경한다. NPC가 새 상황에 반응한다."""
    try:
        session = _get_session(session_id)
    except KeyError as e:
        return {"success": False, "error": str(e)}

    # 시스템 프롬프트 재빌드
    loader = _get_loader()
    builder = PromptBuilder(loader, prompt_override_dir=_DEFAULT_PROMPT_OVERRIDE_DIR)
    new_prompt = builder.build(
        session.character_id, lang=session.language, situation=situation
    )
    if new_prompt is None:
        return {"success": False, "error": "캐릭터 프롬프트 재빌드 실패"}
    session.system_prompt = new_prompt

    # 상황 변경을 대화에 반영
    situation_msg = f"[Situation changed: {situation}]\nReact to this new situation naturally, in character."
    session.messages.append({"role": "user", "content": situation_msg})

    _maybe_compress(session)
    api_messages = _build_api_messages(session)
    reply = _call_claude(session.system_prompt, api_messages)
    session.messages.append({"role": "assistant", "content": reply})

    return {
        "success": True,
        "session_id": session_id,
        "situation": situation,
        "message": reply,
    }


def npc_close_session(session_id: str) -> dict[str, Any]:
    """세션을 종료하고 대화 이력을 반환한다."""
    try:
        session = _get_session(session_id)
    except KeyError as e:
        return {"success": False, "error": str(e)}

    history = [
        {"role": m["role"], "content": m["content"]} for m in session.messages
    ]
    result = {
        "success": True,
        "session_id": session_id,
        "character_id": session.character_id,
        "language": session.language,
        "turn_count": len(history),
        "history": history,
    }
    del _sessions[session_id]
    return result


def npc_get_history(session_id: str) -> dict[str, Any]:
    """세션의 대화 이력을 조회한다 (세션 유지)."""
    try:
        session = _get_session(session_id)
    except KeyError as e:
        return {"success": False, "error": str(e)}

    history = [
        {"role": m["role"], "content": m["content"]} for m in session.messages
    ]
    return {
        "success": True,
        "session_id": session_id,
        "character_id": session.character_id,
        "turn_count": len(history),
        "has_digest": bool(session.digest),
        "history": history,
    }
