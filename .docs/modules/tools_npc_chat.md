# tools/npc_chat.py

> 경로: `seosoyoung/mcp/tools/npc_chat.py`

## 개요

NPC 대화 모듈: 캐릭터 로더, 프롬프트 빌더, npc_list_characters 도구.

## 클래스

### `CharacterLoader`
- 위치: 줄 25
- 설명: eb_lore 캐릭터 YAML 파일을 로드하고 필드를 추출한다.

#### 메서드

- `__init__(self, characters_dir)` (줄 28): 
- `load_all(self)` (줄 33): 모든 캐릭터 YAML을 로드하여 {id: data} 딕셔너리로 반환.
- `get(self, character_id)` (줄 46): 캐릭터 ID로 원본 데이터를 반환. 없으면 None.
- `extract_fields(self, character_id, lang)` (줄 51): 프롬프트 빌더에 필요한 필드를 언어별로 추출.
- `list_chat_ready(self)` (줄 95): 대화 가능한(speech_guide + example_lines 보유) 캐릭터 목록 반환.

### `PromptBuilder`
- 위치: 줄 121
- 설명: 캐릭터 데이터를 프롬프트 템플릿에 채워 시스템 프롬프트를 생성한다.

#### 메서드

- `__init__(self, loader, template_path)` (줄 124): 
- `_load_template(self)` (줄 133): 
- `build(self, character_id, lang, situation)` (줄 138): 캐릭터 ID와 언어로 시스템 프롬프트를 생성. 캐릭터가 없으면 None.

## 함수

### `_get_loader()`
- 위치: 줄 161

### `npc_list_characters()`
- 위치: 줄 171
- 설명: 대화 가능한 NPC 캐릭터 목록을 반환한다.
