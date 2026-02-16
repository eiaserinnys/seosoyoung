"""eb_lore 인덱서 — YAML → Whoosh lore index.

eb_lore/content/ 하위의 characters, glossary, places, synopsis를
파싱하여 Whoosh 인덱스로 변환한다.

청크 ID 체계:
- char:{id}:{section}
- glossary:{category}:{term_index}
- place:{id}:{section}
- synopsis:{file_id}:{section}
"""

from pathlib import Path

import yaml
from whoosh.index import create_in, open_dir, exists_in

from .schema import lore_schema

# 스킵할 파일명
_SKIP_FILES = {"actor_code.yaml"}

# kr/en 텍스트를 갖는 섹션으로 인식하기 위한 조건:
# dict이고 "kr" 또는 "en" 키가 있어야 함
# _로 시작하는 키는 메타데이터 (_title, _display 등)


def _extract_text(value) -> tuple[str, str]:
    """값에서 kr/en 텍스트 추출. list면 줄바꿈 연결."""
    if isinstance(value, str):
        return value.strip(), ""
    if isinstance(value, list):
        return "\n".join(str(v) for v in value).strip(), ""
    return "", ""


def _section_text(section_data: dict) -> tuple[str, str]:
    """섹션 dict에서 kr/en 텍스트 추출."""
    kr_raw = section_data.get("kr", "")
    en_raw = section_data.get("en", "")

    if isinstance(kr_raw, list):
        kr = "\n".join(str(v) for v in kr_raw)
    else:
        kr = str(kr_raw) if kr_raw else ""

    if isinstance(en_raw, list):
        en = "\n".join(str(v) for v in en_raw)
    else:
        en = str(en_raw) if en_raw else ""

    return kr.strip(), en.strip()


def _is_content_section(key: str, value) -> bool:
    """kr/en 텍스트를 포함하는 콘텐츠 섹션인지 판단."""
    if key.startswith("_") or not isinstance(value, dict):
        return False
    return "kr" in value or "en" in value


class LoreIndexer:
    """eb_lore YAML → Whoosh lore index."""

    def __init__(self, lore_path: str | Path, index_path: str | Path):
        self.lore_path = Path(lore_path)
        self.content_path = self.lore_path / "content"
        self.index_path = Path(index_path)

    def index_all(self, force: bool = False) -> dict:
        """모든 로어 데이터 인덱싱."""
        self.index_path.mkdir(parents=True, exist_ok=True)

        if force or not exists_in(str(self.index_path)):
            self.ix = create_in(str(self.index_path), lore_schema)
        else:
            self.ix = open_dir(str(self.index_path))

        writer = self.ix.writer()
        stats = {"characters": 0, "glossary": 0, "places": 0, "synopsis": 0, "errors": []}

        stats["characters"] = self._index_characters(writer, stats["errors"])
        stats["glossary"] = self._index_glossary(writer, stats["errors"])
        stats["places"] = self._index_places(writer, stats["errors"])
        stats["synopsis"] = self._index_synopsis(writer, stats["errors"])

        writer.commit()
        return stats

    def _index_characters(self, writer, errors: list) -> int:
        """캐릭터 YAML 인덱싱."""
        chars_path = self.content_path / "characters"
        if not chars_path.exists():
            return 0

        count = 0
        for yaml_file in chars_path.glob("*.yaml"):
            if yaml_file.name in _SKIP_FILES:
                continue
            try:
                count += self._index_entity(writer, yaml_file, "character")
            except Exception as e:
                errors.append(f"characters/{yaml_file.name}: {e}")
        return count

    def _index_places(self, writer, errors: list) -> int:
        """장소 YAML 인덱싱."""
        places_path = self.content_path / "places"
        if not places_path.exists():
            return 0

        count = 0
        for yaml_file in places_path.glob("*.yaml"):
            try:
                count += self._index_entity(writer, yaml_file, "place")
            except Exception as e:
                errors.append(f"places/{yaml_file.name}: {e}")
        return count

    def _index_synopsis(self, writer, errors: list) -> int:
        """시놉시스 YAML 인덱싱."""
        synopsis_path = self.content_path / "synopsis"
        if not synopsis_path.exists():
            return 0

        count = 0
        for yaml_file in synopsis_path.glob("*.yaml"):
            try:
                count += self._index_entity(writer, yaml_file, "synopsis")
            except Exception as e:
                errors.append(f"synopsis/{yaml_file.name}: {e}")
        return count

    def _index_entity(self, writer, yaml_file: Path, source_type: str) -> int:
        """캐릭터/장소/시놉시스 YAML 파싱 및 인덱싱.

        최상위 dict에서 kr/en을 갖는 섹션을 찾아 각각 하나의 청크로 인덱싱.
        """
        with open(yaml_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            return 0

        entity_id = data.get("id", yaml_file.stem)

        # 이름 추출
        name_data = data.get("name") or data.get("title") or {}
        if isinstance(name_data, dict):
            name_kr = str(name_data.get("kr", ""))
            name_en = str(name_data.get("en", ""))
        else:
            name_kr, name_en = "", ""

        # 청크 ID 접두사
        if source_type == "character":
            prefix = f"char:{entity_id}"
        elif source_type == "place":
            prefix = f"place:{entity_id}"
        else:
            prefix = f"synopsis:{entity_id}"

        count = 0
        for key, value in data.items():
            if not _is_content_section(key, value):
                continue

            # name/title은 별도로 이름 필드에 이미 포함
            if key in ("name", "title", "id"):
                continue

            text_kr, text_en = _section_text(value)
            if not text_kr and not text_en:
                continue

            chunk_id = f"{prefix}:{key}"
            writer.add_document(
                chunk_id=chunk_id,
                source_type=source_type,
                source_id=entity_id,
                section=key,
                name_kr=name_kr,
                name_en=name_en,
                text_kr=text_kr,
                text_en=text_en,
                source_file=str(yaml_file.relative_to(self.lore_path)),
            )
            count += 1

        return count

    def _index_glossary(self, writer, errors: list) -> int:
        """용어집 YAML 인덱싱."""
        glossary_file = self.content_path / "glossary.yaml"
        if not glossary_file.exists():
            return 0

        try:
            with open(glossary_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            errors.append(f"glossary.yaml: {e}")
            return 0

        if not data or not isinstance(data, dict):
            return 0

        count = 0
        for category_key, category_data in data.items():
            if not isinstance(category_data, dict):
                continue
            items = category_data.get("items")
            if not isinstance(items, list):
                continue

            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue

                name_data = item.get("name", {})
                desc_data = item.get("description", {})

                if isinstance(name_data, dict):
                    name_kr = str(name_data.get("kr", ""))
                    name_en = str(name_data.get("en", ""))
                else:
                    name_kr = str(name_data) if name_data else ""
                    name_en = ""

                if isinstance(desc_data, dict):
                    desc_kr = str(desc_data.get("kr", ""))
                    desc_en = str(desc_data.get("en", ""))
                else:
                    desc_kr = str(desc_data) if desc_data else ""
                    desc_en = ""

                if not name_kr and not name_en and not desc_kr and not desc_en:
                    continue

                chunk_id = f"glossary:{category_key}:{idx}"
                writer.add_document(
                    chunk_id=chunk_id,
                    source_type="glossary",
                    source_id="glossary",
                    section=category_key,
                    name_kr=name_kr,
                    name_en=name_en,
                    text_kr=f"{name_kr}\n{desc_kr}".strip(),
                    text_en=f"{name_en}\n{desc_en}".strip(),
                    source_file="content/glossary.yaml",
                )
                count += 1

        return count
