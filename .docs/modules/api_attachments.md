# api/attachments.py

> 경로: `seosoyoung/soul/api/attachments.py`

## 개요

Attachments API - 첨부 파일 관리 엔드포인트

## 함수

### `async upload_attachment(file, thread_id, _)`
- 위치: 줄 27
- 데코레이터: router.post
- 설명: 첨부 파일 업로드

### `async cleanup_attachments(thread_id, _)`
- 위치: 줄 83
- 데코레이터: router.delete
- 설명: 스레드의 첨부 파일 정리

## 내부 의존성

- `seosoyoung.soul.api.auth.verify_token`
- `seosoyoung.soul.models.AttachmentCleanupResponse`
- `seosoyoung.soul.models.AttachmentUploadResponse`
- `seosoyoung.soul.models.ErrorResponse`
- `seosoyoung.soul.service.AttachmentError`
- `seosoyoung.soul.service.file_manager`
