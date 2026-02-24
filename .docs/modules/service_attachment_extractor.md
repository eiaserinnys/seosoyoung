# service/attachment_extractor.py

> 경로: `seosoyoung/soul/service/attachment_extractor.py`

## 개요

첨부 파일 추출 모듈

Claude Code 출력에서 [ATTACH:path] 패턴을 찾아 첨부 파일을 추출하고
보안 검증을 수행합니다.

## 클래스

### `AttachmentExtractor`
- 위치: 줄 15
- 설명: 첨부 파일 추출기

출력 텍스트에서 [ATTACH:path] 패턴을 찾아 안전한 첨부 파일 경로를 추출합니다.

#### 메서드

- `__init__(self, workspace_dir)` (줄 22): Args:
- `extract_attachments(self, text)` (줄 29): 출력에서 [ATTACH:path] 패턴을 추출합니다.
- `is_safe_attachment_path(self, path)` (줄 50): 첨부 파일 경로가 안전한지 검증합니다.

## 내부 의존성

- `seosoyoung.soul.constants.DANGEROUS_EXTENSIONS`
- `seosoyoung.soul.constants.MAX_ATTACHMENT_SIZE`
