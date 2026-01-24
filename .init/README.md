# 초기화 스크립트

리포지토리 clone 후 개발 환경을 설정하는 스크립트입니다.

## 설치

```powershell
# Windows
.init\install.ps1
```

```bash
# Linux/Mac
.init/install.sh
```

## 포함된 hooks

| Hook | 설명 |
|------|------|
| `pre-commit` | Python 소스 변경 시 `.docs/` 문서 자동 생성 |
