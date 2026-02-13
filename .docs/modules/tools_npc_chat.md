# tools/npc_chat.py

> 경로: `seosoyoung/mcp/tools/npc_chat.py`

## 개요

NPC 대화 모듈: 캐릭터 로더, 프롬프트 빌더, 세션 관리, Claude API 연동.

## 클래스

### `CharacterLoader`
- 위치: 줄 30
- 설명: eb_lore 캐릭터 YAML 파일을 로드하고 필드를 추출한다.

#### 메서드

- `__init__(self, characters_dir)` (줄 33): 
- `load_all(self)` (줄 38): 모든 캐릭터 YAML을 로드하여 {id: data} 딕셔너리로 반환.
- `get(self, character_id)` (줄 51): 캐릭터 ID로 원본 데이터를 반환. 없으면 None.
- `extract_fields(self, character_id, lang)` (줄 56): 프롬프트 빌더에 필요한 필드를 언어별로 추출.
- `list_chat_ready(self)` (줄 100): 대화 가능한(speech_guide + example_lines 보유) 캐릭터 목록 반환.

### `PromptBuilder`
- 위치: 줄 126
- 설명: 캐릭터 데이터를 프롬프트 템플릿에 채워 시스템 프롬프트를 생성한다.

#### 메서드

- `__init__(self, loader, template_path, prompt_override_dir)` (줄 129): 
- `_load_template(self, character_id)` (줄 140): 캐릭터별 오버라이드 파일이 있으면 우선 사용, 없으면 기본 템플릿.
- `build(self, character_id, lang, situation)` (줄 150): 캐릭터 ID와 언어로 시스템 프롬프트를 생성. 캐릭터가 없으면 None.

### `NpcSession`
- 위치: 줄 198
- 설명: NPC 대화 세션. 세션별 대화 이력과 설정을 보관한다.

## 함수

### `_get_loader()`
- 위치: 줄 173

### `npc_list_characters()`
- 위치: 줄 183
- 설명: 대화 가능한 NPC 캐릭터 목록을 반환한다.

### `_get_api_key()`
- 위치: 줄 218
- 설명: NPC_CLAUDE_API_KEY 환경변수에서 API 키를 가져온다.

### `_get_client()`
- 위치: 줄 226
- 설명: Anthropic 클라이언트를 생성한다 (lazy import).

### `_call_claude(system_prompt, messages, max_tokens)`
- 위치: 줄 233
- 설명: Claude API를 호출하여 assistant 응답 텍스트를 반환한다.

### `_build_digest(system_prompt, messages)`
- 위치: 줄 249
- 설명: 메시지 목록을 요약하여 다이제스트 텍스트를 생성한다.

### `_get_session(session_id)`
- 위치: 줄 274
- 설명: 세션 ID로 세션을 반환한다. 없으면 KeyError.

### `_maybe_compress(session)`
- 위치: 줄 281
- 설명: 대화 이력이 임계치를 넘으면 다이제스트로 압축한다.

### `_build_api_messages(session)`
- 위치: 줄 298
- 설명: 세션의 다이제스트 + 메시지를 Claude API 호출용 메시지 리스트로 변환한다.

### `npc_open_session(character_id, situation, language)`
- 위치: 줄 317
- 설명: NPC 대화 세션을 열고 NPC의 첫 반응을 반환한다.

### `npc_talk(session_id, message)`
- 위치: 줄 359
- 설명: NPC에게 말하기. 사용자 메시지를 보내고 NPC 응답을 받는다.

### `npc_set_situation(session_id, situation)`
- 위치: 줄 382
- 설명: 대화 중 상황을 변경한다. NPC가 새 상황에 반응한다.

### `npc_close_session(session_id)`
- 위치: 줄 416
- 설명: 세션을 종료하고 대화 이력을 반환한다.

### `npc_get_history(session_id)`
- 위치: 줄 438
- 설명: 세션의 대화 이력을 조회한다 (세션 유지).
