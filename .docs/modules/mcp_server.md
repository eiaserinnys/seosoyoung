# mcp/server.py

> 경로: `seosoyoung/mcp/server.py`

## 개요

seosoyoung MCP 서버 정의

## 함수

### `slack_attach_file(file_path, channel, thread_ts)`
- 위치: 줄 31
- 데코레이터: mcp.tool
- 설명: 슬랙에 파일을 첨부합니다.

workspace(slackbot_workspace) 내부 파일만 허용됩니다.
허용 확장자: .md, .txt, .yaml, .yml, .json, .csv, .png, .jpg, .pdf 등
최대 파일 크기: 20MB

Args:
    file_path: 첨부할 파일의 절대 경로
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프

### `slack_get_context()`
- 위치: 줄 47
- 데코레이터: mcp.tool
- 설명: 현재 슬랙 대화의 채널/스레드 정보를 반환합니다.

환경변수 SLACK_CHANNEL, SLACK_THREAD_TS에서 읽어 반환합니다.
attach_file 호출 전에 컨텍스트를 조회할 때 사용합니다.

### `slack_post_message(channel, text, thread_ts, file_paths)`
- 위치: 줄 57
- 데코레이터: mcp.tool
- 설명: 봇 권한으로 슬랙 채널에 메시지를 보냅니다.

텍스트 전송과 파일 첨부를 모두 지원합니다.
파일 첨부 시 workspace 내부 파일만 허용됩니다.

Args:
    channel: 슬랙 채널 ID (필수)
    text: 메시지 텍스트 (필수)
    thread_ts: 스레드 타임스탬프 (선택)
    file_paths: 파일 경로, 쉼표 구분 (선택)

### `async slack_generate_image(prompt, channel, thread_ts, reference_image_paths)`
- 위치: 줄 78
- 데코레이터: mcp.tool
- 설명: 텍스트 프롬프트로 이미지를 생성하고 슬랙 스레드에 업로드합니다.

Gemini API를 사용하여 이미지를 생성합니다.
레퍼런스 이미지를 전달하면 해당 이미지를 참고하여 생성합니다.

Args:
    prompt: 이미지 생성 프롬프트 (영어 권장)
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프
    reference_image_paths: 레퍼런스 이미지 절대 경로, 쉼표 구분 (선택)

### `async slack_download_thread_files(channel, thread_ts)`
- 위치: 줄 101
- 데코레이터: mcp.tool
- 설명: 스레드 내 모든 메시지의 첨부 파일을 다운로드합니다.

Slack conversations.replies API로 스레드 메시지를 조회하고,
파일이 있는 메시지에서 파일을 로컬로 다운로드합니다.

Args:
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프

### `slack_get_user_profile(user_id)`
- 위치: 줄 115
- 데코레이터: mcp.tool
- 설명: Slack 사용자의 프로필 정보를 조회합니다.

display_name, real_name, title, status, email, 프로필 이미지 URL 등을 반환합니다.

Args:
    user_id: Slack User ID (예: U08HWT0C6K1)

### `async slack_download_user_avatar(user_id, size)`
- 위치: 줄 127
- 데코레이터: mcp.tool
- 설명: Slack 사용자의 프로필 이미지를 다운로드합니다.

지정한 크기의 프로필 이미지를 로컬에 저장하고 절대 경로를 반환합니다.

Args:
    user_id: Slack User ID (예: U08HWT0C6K1)
    size: 이미지 크기 (24, 32, 48, 72, 192, 512, 1024). 기본값 512.

### `npc_list_characters()`
- 위치: 줄 142
- 데코레이터: mcp.tool
- 설명: 대화 가능한 NPC 캐릭터 목록을 반환합니다.

eb_lore 캐릭터 데이터에서 speech_guide와 example_lines가 있는 캐릭터만 포함합니다.
각 캐릭터의 id, name(kr/en), role(kr/en), tagline(있는 경우)을 반환합니다.

### `npc_open_session(character_id, situation, language)`
- 위치: 줄 152
- 데코레이터: mcp.tool
- 설명: NPC 대화 세션을 열고 NPC의 첫 반응을 반환합니다.

캐릭터 ID로 세션을 시작하며, 선택적으로 상황 설명과 언어를 지정할 수 있습니다.
반환값에 session_id가 포함되며, 이후 대화에 사용합니다.

Args:
    character_id: 캐릭터 ID (npc_list_characters로 조회)
    situation: 초기 상황 설명 (선택)
    language: 언어 코드 - "kr" 또는 "en" (기본: "kr")

### `npc_talk(session_id, message)`
- 위치: 줄 171
- 데코레이터: mcp.tool
- 설명: NPC에게 말을 걸고 응답을 받습니다.

세션 내 대화 이력이 누적되며, 임계치를 넘으면 자동으로 다이제스트 압축됩니다.

Args:
    session_id: npc_open_session에서 받은 세션 ID
    message: 사용자 메시지

### `npc_set_situation(session_id, situation)`
- 위치: 줄 184
- 데코레이터: mcp.tool
- 설명: 대화 중 상황을 변경하고 NPC의 반응을 받습니다.

시스템 프롬프트가 새 상황으로 갱신되며, NPC가 변경된 상황에 자연스럽게 반응합니다.

Args:
    session_id: 세션 ID
    situation: 새로운 상황 설명

### `npc_inject(session_id, speaker_name, message)`
- 위치: 줄 197
- 데코레이터: mcp.tool
- 설명: 다른 NPC의 대사를 세션 대화 이력에 주입합니다.

멀티 NPC 대화에서, 다른 세션의 NPC 응답을 현재 세션의 대화 컨텍스트에 추가합니다.
주입된 대사는 다음 npc_talk 호출 시 대화 이력에 포함됩니다.

Args:
    session_id: 대사를 주입할 세션 ID
    speaker_name: 발화자 이름 (예: "펜릭스", "아리엘라")
    message: 주입할 대사 텍스트

### `npc_close_session(session_id)`
- 위치: 줄 212
- 데코레이터: mcp.tool
- 설명: 세션을 종료하고 전체 대화 이력을 반환합니다.

세션이 메모리에서 삭제됩니다. 이후 같은 session_id로 대화할 수 없습니다.

Args:
    session_id: 종료할 세션 ID

### `npc_get_history(session_id)`
- 위치: 줄 224
- 데코레이터: mcp.tool
- 설명: 세션의 대화 이력을 조회합니다 (세션 유지).

세션을 종료하지 않고 현재까지의 대화 이력을 확인합니다.

Args:
    session_id: 세션 ID

### `lore_keyword_search(keywords, speaker, source, top_k)`
- 위치: 줄 236
- 데코레이터: mcp.tool
- 설명: 키워드 기반 로어/대사 검색.

Whoosh 인덱스에서 키워드를 검색하여 chunk_id + 매칭된 스니펫을 반환합니다.
검색 결과의 chunk_id를 lore_chunk_read에 전달하면 전체 텍스트를 읽을 수 있습니다.

Args:
    keywords: 검색 키워드 리스트 (예: ["악마", "사냥"])
    speaker: 화자 필터 — 대사 검색 시 사용 (예: "fx", "ar")
    source: 검색 대상 — "dlg" (대사), "lore" (설정), "all" (전체)
    top_k: 최대 결과 수 (기본 10)

### `lore_semantic_search(query, speaker, source, top_k)`
- 위치: 줄 257
- 데코레이터: mcp.tool
- 설명: 의미 기반 로어/대사 검색.

쿼리 텍스트를 임베딩 벡터로 변환하여 코사인 유사도 기반 검색을 수행합니다.
A-RAG 방식으로 부모 청크 기준 집계하여 반환합니다.
검색 결과의 chunk_id를 lore_chunk_read에 전달하면 전체 텍스트를 읽을 수 있습니다.

Args:
    query: 검색 쿼리 텍스트 (자연어, 예: "계약의 대가에 대한 고민")
    speaker: 화자 필터 — 대사 검색 시 사용 (예: "fx", "ar")
    source: 검색 대상 — "dlg" (대사), "lore" (설정), "all" (전체)
    top_k: 최대 결과 수 (기본 10)

### `lore_chunk_read(chunk_id, include_adjacent)`
- 위치: 줄 279
- 데코레이터: mcp.tool
- 설명: chunk_id로 전체 텍스트를 읽습니다.

keyword_search나 semantic_search 결과의 chunk_id를 전달하면
해당 청크의 전체 한/영 텍스트를 반환합니다.
이미 읽은 청크를 다시 요청하면 토큰 절약을 위해 간략 메시지만 반환합니다.

Args:
    chunk_id: 청크 ID — 대사 ID (예: "fx-008V57I1") 또는 로어 청크 (예: "char:fx:basic_info")
    include_adjacent: True면 인접 대사/섹션도 함께 반환 (기본 False)

## 내부 의존성

- `seosoyoung.mcp.tools.attach.attach_file`
- `seosoyoung.mcp.tools.attach.get_slack_context`
- `seosoyoung.mcp.tools.image_gen.generate_and_upload_image`
- `seosoyoung.mcp.tools.lore_search.lore_chunk_read`
- `seosoyoung.mcp.tools.lore_search.lore_keyword_search`
- `seosoyoung.mcp.tools.lore_search.lore_semantic_search`
- `seosoyoung.mcp.tools.npc_chat.npc_close_session`
- `seosoyoung.mcp.tools.npc_chat.npc_get_history`
- `seosoyoung.mcp.tools.npc_chat.npc_inject`
- `seosoyoung.mcp.tools.npc_chat.npc_list_characters`
- `seosoyoung.mcp.tools.npc_chat.npc_open_session`
- `seosoyoung.mcp.tools.npc_chat.npc_set_situation`
- `seosoyoung.mcp.tools.npc_chat.npc_talk`
- `seosoyoung.mcp.tools.slack_messaging.post_message`
- `seosoyoung.mcp.tools.thread_files.download_thread_files`
- `seosoyoung.mcp.tools.user_profile.download_user_avatar`
- `seosoyoung.mcp.tools.user_profile.get_user_profile`
