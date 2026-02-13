"""NPC 대화 모듈: 캐릭터 로더, 프롬프트 빌더, npc_list_characters 도구."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml


# ── 기본 경로 설정 ──────────────────────────────────────────

_DEFAULT_CHARACTERS_DIR = (
    Path(__file__).resolve().parents[5] / "eb_lore" / "content" / "characters"
)
_DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "npc_system.txt"

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
    ):
        self._loader = loader
        self._template_path = template_path or _DEFAULT_TEMPLATE_PATH
        self._template: Optional[str] = None

    def _load_template(self) -> str:
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
        template = self._load_template()
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
