---
paths: seosoyung/*
---

# 패키지 의존성 관리 규칙

## seosoyoung 프로젝트 모듈 추가 시

Python 패키지를 import하는 코드를 추가할 때:

1. **표준 라이브러리인지 확인**
2. **서드파티 패키지라면 `seosoyoung/requirements.txt`에 반드시 추가**

## requirements.txt 업데이트 방법

```
패키지명>=버전
```

예시:
- `aiohttp>=3.9.0`
- `pyyaml>=6.0`

테스트 전용 의존성은 `# Testing` 섹션에 분리:
```
# Testing
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

## 체크리스트

새 import 추가 시 확인:
- [ ] 표준 라이브러리 여부 확인
- [ ] 서드파티 패키지면 requirements.txt에 추가
- [ ] 버전 지정 (>=x.y.z 형식 권장)
