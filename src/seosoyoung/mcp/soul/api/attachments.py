"""
Attachments API - 첨부 파일 관리 엔드포인트
"""

import logging
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form

from seosoyoung.mcp.soul.models import (
    AttachmentUploadResponse,
    AttachmentCleanupResponse,
    ErrorResponse,
)
from seosoyoung.mcp.soul.service import file_manager, AttachmentError
from seosoyoung.mcp.soul.api.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=AttachmentUploadResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}},
)
async def upload_attachment(
    file: UploadFile = File(...),
    thread_id: int = Form(...),
    _: str = Depends(verify_token),
):
    """
    첨부 파일 업로드
    """
    try:
        # 파일 내용 읽기
        content = await file.read()

        # 파일 저장
        result = await file_manager.save_file(
            thread_id=thread_id,
            filename=file.filename or "unnamed",
            content=content,
        )

        return AttachmentUploadResponse(
            path=result["path"],
            filename=result["filename"],
            size=result["size"],
            content_type=result["content_type"],
        )

    except AttachmentError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": str(e),
                    "details": {},
                }
            },
        )

    except Exception as e:
        logger.exception(f"Attachment upload error: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": f"파일 업로드 실패: {str(e)}",
                    "details": {},
                }
            },
        )


@router.delete(
    "/{thread_id}",
    response_model=AttachmentCleanupResponse,
)
async def cleanup_attachments(
    thread_id: int,
    _: str = Depends(verify_token),
):
    """
    스레드의 첨부 파일 정리
    """
    files_removed = file_manager.cleanup_thread(thread_id)

    return AttachmentCleanupResponse(
        cleaned=True,
        files_removed=files_removed,
    )
