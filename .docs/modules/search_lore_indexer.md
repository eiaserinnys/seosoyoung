# search/lore_indexer.py

> 경로: `seosoyoung/search/lore_indexer.py`

## 개요

eb_lore 인덱서 — YAML → Whoosh lore index.

eb_lore/content/ 하위의 characters, glossary, places, synopsis를
파싱하여 Whoosh 인덱스로 변환한다.

청크 ID 체계:
- char:{id}:{section}
- glossary:{category}:{term_index}
- place:{id}:{section}
- synopsis:{file_id}:{section}

## 클래스

### `LoreIndexer`
- 위치: 줄 62
- 설명: eb_lore YAML → Whoosh lore index.

#### 메서드

- `__init__(self, lore_path, index_path)` (줄 65): 
- `index_all(self, force)` (줄 70): 모든 로어 데이터 인덱싱.
- `_index_characters(self, writer, errors)` (줄 90): 캐릭터 YAML 인덱싱.
- `_index_places(self, writer, errors)` (줄 106): 장소 YAML 인덱싱.
- `_index_synopsis(self, writer, errors)` (줄 120): 시놉시스 YAML 인덱싱.
- `_index_entity(self, writer, yaml_file, source_type)` (줄 134): 캐릭터/장소/시놉시스 YAML 파싱 및 인덱싱.
- `_index_glossary(self, writer, errors)` (줄 192): 용어집 YAML 인덱싱.

## 함수

### `_extract_text(value)`
- 위치: 줄 28
- 설명: 값에서 kr/en 텍스트 추출. list면 줄바꿈 연결.

### `_section_text(section_data)`
- 위치: 줄 37
- 설명: 섹션 dict에서 kr/en 텍스트 추출.

### `_is_content_section(key, value)`
- 위치: 줄 55
- 설명: kr/en 텍스트를 포함하는 콘텐츠 섹션인지 판단.
