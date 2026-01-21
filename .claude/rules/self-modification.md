---
paths: seosoyung/*
---

# 봇 코드 수정 (자기 수정)

사용자가 **서소영 봇 자체의 코드 수정**을 요청하는 경우 다음 워크플로우를 따릅니다.

## 작업 경로

- 봇 코드 수정은 `./seosoyoung` 폴더에서 진행
  - 이 폴더는 https://github.com/eias/seosoyoung 저장소의 클론

## Git 동기화 (작업 전 필수)

코드 작업 전 반드시 원격 저장소와 동기화:

```bash
# seosoyoung 저장소
git -C ./seosoyoung fetch origin && git -C ./seosoyoung status
git -C ./seosoyoung pull origin main  # 원격이 앞서 있으면
```

## 워크플로우

1. **브랜치 생성**: main에서 새 브랜치 생성
   ```bash
   git -C ./seosoyoung fetch origin
   git -C ./seosoyoung checkout main
   git -C ./seosoyoung pull origin main
   git -C ./seosoyoung checkout -b feature/카드ID-설명
   ```

2. **코드 수정**: `./seosoyoung/src/seosoyoung/` 내 파일 수정
   작업 시 항상 작업 내역을 검증할 수 있는 테스트 케이스를 작성

3. **테스트 실행**:
   ```bash
   python -m pytest ./seosoyoung
   ```

4. **커밋**:
   ```bash
   git -C ./seosoyoung add -A && git -C ./seosoyoung commit -m "변경 내용"
   ```

5. **머지 및 푸시**:
   ```bash
   git -C ./seosoyoung checkout main
   git -C ./seosoyoung pull origin main
   git -C ./seosoyoung merge feature/카드ID-설명 --no-ff -m "Merge: 변경 내용"
   git -C ./seosoyoung push origin main
   git -C ./seosoyoung branch -d feature/카드ID-설명
   ```

6. **재기동 요청**: 응답 끝에 업데이트 마커 추가
   ```
   <!-- UPDATE -->
   ```

## 브랜치 명명 규칙

| 접두사 | 용도 | 예시 |
|--------|------|------|
| `feature/` | 새 기능 추가 | `feature/696ec479-branch-workflow` |
| `fix/` | 버그 수정 | `fix/696ec480-encoding-error` |
| `refactor/` | 리팩토링 | `refactor/696ec481-cleanup-handlers` |

**형식**: `<접두사><카드ID 앞 8자>-<간단한-설명>`

## 재기동 마커

| 마커 | 동작 | 용도 |
|------|------|------|
| `<!-- UPDATE -->` | git pull 후 재시작 | 코드 수정 후 |
| `<!-- RESTART -->` | 단순 재시작 | 설정 변경 등 |

**주의:**
- 마커는 **admin 역할**인 경우에만 동작
- 테스트 통과 후에만 마커 사용
