# service/credential_swapper.py

> 경로: `seosoyoung/soul/service/credential_swapper.py`

## 개요

CredentialSwapper - 크레덴셜 파일 교체 모듈

~/.claude/.credentials.json 파일을 프로필별로 교체합니다.
- 현재 활성 크레덴셜을 프로필로 저장 (save)
- 지정된 프로필의 크레덴셜로 교체 (activate)
- 원자적 교체 (임시 파일 → rename)

## 클래스

### `CredentialSwapper`
- 위치: 줄 20
- 설명: 크레덴셜 파일 교체기.

credentials_path의 파일을 읽고 쓰며,
CredentialStore를 통해 프로필 저장/조회/활성 추적을 처리합니다.

#### 메서드

- `__init__(self, store, credentials_path)` (줄 28): 
- `read_current(self)` (줄 36): 현재 크레덴셜 파일을 읽어 반환.
- `save_current_as(self, name)` (줄 52): 현재 크레덴셜을 프로필로 저장.
- `activate(self, name)` (줄 68): 지정된 프로필의 크레덴셜로 교체.

## 내부 의존성

- `seosoyoung.soul.service.credential_store.CredentialStore`
