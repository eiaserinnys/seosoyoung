# mcp/server.py

> 경로: `seosoyoung/mcp/server.py`

## 개요

seosoyoung MCP 서버 정의

## 함수

### `slack_attach_file(file_path, channel, thread_ts)`
- 위치: 줄 18
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
- 위치: 줄 34
- 데코레이터: mcp.tool
- 설명: 현재 슬랙 대화의 채널/스레드 정보를 반환합니다.

환경변수 SLACK_CHANNEL, SLACK_THREAD_TS에서 읽어 반환합니다.
attach_file 호출 전에 컨텍스트를 조회할 때 사용합니다.

### `slack_post_message(channel, text, thread_ts, file_paths)`
- 위치: 줄 44
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
- 위치: 줄 65
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
- 위치: 줄 88
- 데코레이터: mcp.tool
- 설명: 스레드 내 모든 메시지의 첨부 파일을 다운로드합니다.

Slack conversations.replies API로 스레드 메시지를 조회하고,
파일이 있는 메시지에서 파일을 로컬로 다운로드합니다.

Args:
    channel: 슬랙 채널 ID
    thread_ts: 스레드 타임스탬프

### `slack_get_user_profile(user_id)`
- 위치: 줄 102
- 데코레이터: mcp.tool
- 설명: Slack 사용자의 프로필 정보를 조회합니다.

display_name, real_name, title, status, email, 프로필 이미지 URL 등을 반환합니다.

Args:
    user_id: Slack User ID (예: U08HWT0C6K1)

### `async slack_download_user_avatar(user_id, size)`
- 위치: 줄 114
- 데코레이터: mcp.tool
- 설명: Slack 사용자의 프로필 이미지를 다운로드합니다.

지정한 크기의 프로필 이미지를 로컬에 저장하고 절대 경로를 반환합니다.

Args:
    user_id: Slack User ID (예: U08HWT0C6K1)
    size: 이미지 크기 (24, 32, 48, 72, 192, 512, 1024). 기본값 512.

### `npc_list_characters()`
- 위치: 줄 129
- 데코레이터: mcp.tool
- 설명: 대화 가능한 NPC 캐릭터 목록을 반환합니다.

eb_lore 캐릭터 데이터에서 speech_guide와 example_lines가 있는 캐릭터만 포함합니다.
각 캐릭터의 id, name(kr/en), role(kr/en), tagline(있는 경우)을 반환합니다.

## 내부 의존성

- `seosoyoung.mcp.tools.attach.attach_file`
- `seosoyoung.mcp.tools.attach.get_slack_context`
- `seosoyoung.mcp.tools.image_gen.generate_and_upload_image`
- `seosoyoung.mcp.tools.npc_chat.npc_list_characters`
- `seosoyoung.mcp.tools.slack_messaging.post_message`
- `seosoyoung.mcp.tools.thread_files.download_thread_files`
- `seosoyoung.mcp.tools.user_profile.download_user_avatar`
- `seosoyoung.mcp.tools.user_profile.get_user_profile`
