# profile/manager.py

> 경로: `seosoyoung/profile/manager.py`

## 개요

Claude Code 인증 프로필 관리

~/.claude/.credentials.json 파일을 스왑하여 계정을 전환한다.

## 클래스

### `ProfileInfo`
- 위치: 줄 14
- 설명: 프로필 정보

### `ProfileManager`
- 위치: 줄 24
- 설명: Claude Code 인증 프로필 관리자

Args:
    profiles_dir: 프로필 저장 디렉토리 (.local/profiles/)
    credentials_path: Claude 인증 파일 경로 (~/.claude/.credentials.json)

#### 메서드

- `__init__(self, profiles_dir, credentials_path)` (줄 32): 
- `_validate_name(self, name)` (줄 36): 프로필 이름 유효성 검증
- `_active_file(self)` (줄 47): 
- `_get_active_name(self)` (줄 50): 
- `_set_active_name(self, name)` (줄 56): 
- `_clear_active(self)` (줄 59): 
- `list_profiles(self)` (줄 64): 저장된 프로필 목록 반환 (활성 프로필 표시)
- `save_profile(self, name)` (줄 78): 현재 인증을 프로필로 저장
- `change_profile(self, name)` (줄 110): 저장된 프로필로 전환
- `delete_profile(self, name)` (줄 142): 프로필 삭제
