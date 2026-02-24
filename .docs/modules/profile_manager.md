# profile/manager.py

> 경로: `seosoyoung/slackbot/profile/manager.py`

## 개요

Claude Code 인증 프로필 관리 (CLAUDE_CONFIG_DIR + Junction 방식)

각 프로필은 독립된 디렉토리로 관리되며, CLAUDE_CONFIG_DIR 환경변수로 지정된다.
세션 히스토리(projects/, todos/, plans/)는 .shared/ 폴더에 원본을 두고
각 프로필 디렉토리에 Windows Junction으로 연결하여 공유한다.

## 클래스

### `ProfileInfo`
- 위치: 줄 23
- 설명: 프로필 정보

### `ProfileManager`
- 위치: 줄 33
- 설명: Claude Code 인증 프로필 관리자 (CLAUDE_CONFIG_DIR + Junction)

디렉토리 구조:
    profiles_dir/
    ├── .shared/              ← 공유 데이터 원본
    │   ├── projects/
    │   ├── todos/
    │   └── plans/
    ├── _active.txt           ← 활성 프로필 이름
    ├── work/                 ← 프로필 폴더 (CLAUDE_CONFIG_DIR로 지정)
    │   ├── .credentials.json
    │   ├── settings.json
    │   ├── projects/         ← Junction → .shared/projects
    │   ├── todos/            ← Junction → .shared/todos
    │   └── plans/            ← Junction → .shared/plans
    └── personal/             ← 동일 구조

Args:
    profiles_dir: 프로필 저장 디렉토리 (.local/claude_profiles/)

#### 메서드

- `__init__(self, profiles_dir)` (줄 55): 
- `profiles_dir(self)` (줄 59): 
- `_shared_dir(self)` (줄 63): 
- `_validate_name(self, name)` (줄 66): 
- `_active_file(self)` (줄 76): 
- `_profile_dir(self, name)` (줄 79): 
- `_get_active_name(self)` (줄 82): 
- `_set_active_name(self, name)` (줄 88): 
- `_clear_active(self)` (줄 92): 
- `_ensure_shared_dir(self, source_dir)` (줄 97): 공유 디렉토리 초기화. source_dir에서 기존 데이터를 복사.
- `_create_junction(self, link_path, target_path)` (줄 110): Windows Junction 생성 (mklink /J)
- `_setup_junctions(self, profile_dir)` (줄 128): 프로필 디렉토리에 공유 디렉토리 Junction 생성
- `_remove_junctions(self, profile_dir)` (줄 136): 프로필 디렉토리의 Junction 제거 (rmdir로 Junction만 제거, 원본 보존)
- `list_profiles(self)` (줄 151): 저장된 프로필 목록 반환
- `save_profile(self, name, source_dir)` (줄 171): 프로필 저장 (소스 디렉토리에서 인증 정보 복사 + Junction 설정)
- `change_profile(self, name)` (줄 214): 활성 프로필 변경 (재시작 시 CLAUDE_CONFIG_DIR이 이 프로필을 가리킴)
- `get_config_dir(self, name)` (줄 232): 프로필의 CLAUDE_CONFIG_DIR 경로 반환
- `get_active_config_dir(self)` (줄 251): 활성 프로필의 CLAUDE_CONFIG_DIR 경로 반환. 없으면 None.
- `delete_profile(self, name)` (줄 261): 프로필 삭제
