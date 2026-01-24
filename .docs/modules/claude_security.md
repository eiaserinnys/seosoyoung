# claude/security.py

> 경로: `seosoyoung/claude/security.py`

## 개요

보안 레이어

기존에 프롬프트 인젝션 방어, 출력 마스킹, 경로 제한 등을 처리했으나,
이러한 검사는 오탐 및 우회 가능성이 있어 제거되었습니다.

보안 관련 지침은 슬랙봇 워크스페이스의 .claude/rules/ 폴더에서 관리합니다.

## 클래스

### `SecurityError` (Exception)
- 위치: 줄 10
- 설명: 보안 관련 에러
