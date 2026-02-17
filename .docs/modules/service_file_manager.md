# service/file_manager.py

> 경로: `seosoyoung/mcp/soul/service/file_manager.py`

## 개요

FileManager - 첨부 파일 관리

첨부 파일 업로드, 검증, 정리를 담당합니다.

## 클래스

### `AttachmentError` (Exception)
- 위치: 줄 23
- 설명: 첨부 파일 처리 오류

### `FileManager`
- 위치: 줄 28
- 설명: 첨부 파일 관리자

역할:
1. 첨부 파일 저장 (스레드별 격리)
2. 파일 검증 (크기, 확장자)
3. 스레드 첨부 파일 정리

#### 메서드

- `__init__(self, base_dir, max_size)` (줄 38): Args:
- `get_thread_dir(self, thread_id)` (줄 54): 스레드별 첨부 파일 디렉토리
- `validate_file(self, filename, size)` (줄 60): 파일 검증
- `async save_file(self, thread_id, filename, content)` (줄 84): 파일 저장
- `is_safe_path(self, path, workspace_dir)` (줄 129): 파일 경로 보안 검증
- `cleanup_thread(self, thread_id)` (줄 183): 스레드의 첨부 파일 정리
- `cleanup_old_files(self, max_age_hours)` (줄 206): 오래된 첨부 파일 정리
- `get_stats(self)` (줄 238): 첨부 파일 통계

## 내부 의존성

- `seosoyoung.mcp.soul.constants.DANGEROUS_EXTENSIONS`
- `seosoyoung.mcp.soul.constants.MAX_ATTACHMENT_SIZE`
