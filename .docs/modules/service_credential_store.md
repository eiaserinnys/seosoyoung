# service/credential_store.py

> 경로: `seosoyoung/soul/service/credential_store.py`

## 개요

CredentialStore - 프로필별 크레덴셜 저장소

프로필별 credentials.json 저장/조회/삭제 및 활성 프로필 추적.
저장 경로: {profiles_dir}/{name}.json
활성 프로필 추적: {profiles_dir}/_active.txt

## 클래스

### `CredentialStore`
- 위치: 줄 27
- 설명: 프로필별 크레덴셜 저장소.

각 프로필은 {profiles_dir}/{name}.json 파일로 저장되며,
활성 프로필은 {profiles_dir}/_active.txt 파일에 기록됩니다.

#### 메서드

- `__init__(self, profiles_dir)` (줄 35): 
- `profiles_dir(self)` (줄 41): 프로필 저장 디렉토리 경로.
- `_validate_name(self, name)` (줄 45): 프로필 이름 유효성 검사.
- `_profile_path(self, name)` (줄 58): 
- `save(self, name, credentials)` (줄 61): 프로필 저장.
- `get(self, name)` (줄 95): 프로필 조회.
- `delete(self, name)` (줄 118): 프로필 삭제.
- `set_active(self, name)` (줄 147): 활성 프로필 설정.
- `get_active(self)` (줄 164): 현재 활성 프로필 이름 조회.
- `clear_active(self)` (줄 184): 활성 프로필 해제.
- `list_profiles(self)` (줄 189): 저장된 모든 프로필의 메타데이터 목록 조회.
