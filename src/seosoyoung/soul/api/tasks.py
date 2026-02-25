"""
Tasks API - 태스크 기반 API 엔드포인트

기존 세션 기반 API를 대체하는 새 API.
클라이언트 재시작 시에도 결과를 복구할 수 있도록 설계됨.
"""

import asyncio
import logging
import json
from fastapi import APIRouter, HTTPException, Depends
from sse_starlette.sse import EventSourceResponse

from seosoyoung.soul.models import (
    ExecuteRequest,
    TaskResponse,
    TaskListResponse,
    TaskInterveneRequest,
    InterveneResponse,
    ErrorResponse,
)
from seosoyoung.soul.service.task_manager import (
    get_task_manager,
    Task,
    TaskConflictError,
    TaskNotFoundError,
    TaskNotRunningError,
    TaskStatus,
)
from seosoyoung.soul.service import resource_manager, soul_engine
from seosoyoung.soul.api.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter()


def task_to_response(task: Task) -> TaskResponse:
    """Task를 TaskResponse로 변환"""
    from seosoyoung.soul.models import TaskStatus as ResponseTaskStatus
    return TaskResponse(
        client_id=task.client_id,
        request_id=task.request_id,
        status=ResponseTaskStatus(task.status.value),
        result=task.result,
        error=task.error,
        claude_session_id=task.claude_session_id,
        result_delivered=task.result_delivered,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


@router.post(
    "/execute",
    responses={
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def execute_task(
    request: ExecuteRequest,
    _: str = Depends(verify_token),
):
    """
    Claude Code 실행 (SSE 스트리밍)

    태스크를 생성하고 Claude Code를 백그라운드에서 실행합니다.
    결과는 SSE로 스트리밍되며, 클라이언트 연결이 끊어져도
    백그라운드 실행은 계속되고 결과는 보관되어 나중에 조회할 수 있습니다.
    """
    task_manager = get_task_manager()

    # 동시 실행 제한 확인
    if not resource_manager.can_acquire():
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"동시 실행 제한 초과 (max={resource_manager.max_concurrent})",
                    "details": {},
                }
            },
        )

    # 태스크 생성
    try:
        task = await task_manager.create_task(
            client_id=request.client_id,
            request_id=request.request_id,
            prompt=request.prompt,
            resume_session_id=request.resume_session_id,
        )
    except TaskConflictError:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "TASK_CONFLICT",
                    "message": f"이미 실행 중인 태스크가 있습니다: {request.client_id}:{request.request_id}",
                    "details": {},
                }
            },
        )

    # 백그라운드에서 Claude 실행 시작
    await task_manager.start_execution(
        client_id=request.client_id,
        request_id=request.request_id,
        claude_runner=soul_engine,
        resource_manager=resource_manager,
    )

    async def event_generator():
        """SSE 이벤트 생성기 (리스너로서 이벤트 수신)"""
        event_queue = asyncio.Queue()
        await task_manager.add_listener(request.client_id, request.request_id, event_queue)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)
                    yield {
                        "event": event.get("type", "unknown"),
                        "data": json.dumps(event, ensure_ascii=False),
                    }

                    # 완료 또는 에러면 종료
                    if event.get("type") in ["complete", "error"]:
                        break

                except asyncio.TimeoutError:
                    # keepalive (빈 코멘트)
                    yield {"comment": "keepalive"}

        finally:
            await task_manager.remove_listener(
                request.client_id, request.request_id, event_queue
            )

    return EventSourceResponse(event_generator())


@router.get(
    "/tasks/{client_id}",
    response_model=TaskListResponse,
)
async def get_tasks(
    client_id: str,
    _: str = Depends(verify_token),
):
    """
    클라이언트의 태스크 목록 조회

    클라이언트가 재시작 후 미전달 결과를 확인하는 데 사용합니다.
    """
    task_manager = get_task_manager()
    tasks = await task_manager.get_tasks_by_client(client_id)

    return TaskListResponse(
        tasks=[task_to_response(task) for task in tasks]
    )


@router.get(
    "/tasks/{client_id}/{request_id}",
    response_model=TaskResponse,
    responses={404: {"model": ErrorResponse}},
)
async def get_task(
    client_id: str,
    request_id: str,
    _: str = Depends(verify_token),
):
    """
    특정 태스크 조회
    """
    task_manager = get_task_manager()
    task = await task_manager.get_task(client_id, request_id)

    if not task:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"태스크를 찾을 수 없습니다: {client_id}:{request_id}",
                    "details": {},
                }
            },
        )

    return task_to_response(task)


@router.get(
    "/tasks/{client_id}/{request_id}/stream",
    responses={404: {"model": ErrorResponse}},
)
async def reconnect_stream(
    client_id: str,
    request_id: str,
    _: str = Depends(verify_token),
):
    """
    태스크 SSE 스트림에 재연결

    running 태스크: 현재 상태 전송 후 진행 중인 이벤트를 계속 수신
    completed 태스크: 저장된 결과를 즉시 반환
    error 태스크: 저장된 에러를 즉시 반환
    """
    task_manager = get_task_manager()
    task = await task_manager.get_task(client_id, request_id)

    if not task:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"태스크를 찾을 수 없습니다: {client_id}:{request_id}",
                    "details": {},
                }
            },
        )

    async def event_generator():
        # 이미 완료된 태스크면 즉시 결과 반환
        if task.status == TaskStatus.COMPLETED:
            yield {
                "event": "complete",
                "data": json.dumps({
                    "type": "complete",
                    "result": task.result,
                    "claude_session_id": task.claude_session_id,
                    "attachments": [],
                }, ensure_ascii=False),
            }
            return

        if task.status == TaskStatus.ERROR:
            yield {
                "event": "error",
                "data": json.dumps({
                    "type": "error",
                    "message": task.error,
                }, ensure_ascii=False),
            }
            return

        # running 태스크면 리스너 등록하고 이벤트 대기
        event_queue = asyncio.Queue()
        await task_manager.add_listener(client_id, request_id, event_queue)

        try:
            # 재연결 시 현재 상태 이벤트 전송
            await task_manager.send_reconnect_status(client_id, request_id, event_queue)

            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30.0)

                    # reconnected 이벤트도 클라이언트에 전달
                    yield {
                        "event": event.get("type", "unknown"),
                        "data": json.dumps(event, ensure_ascii=False),
                    }

                    # 완료 또는 에러면 종료
                    if event.get("type") in ["complete", "error"]:
                        break

                except asyncio.TimeoutError:
                    # keepalive (빈 코멘트)
                    yield {"comment": "keepalive"}

        finally:
            await task_manager.remove_listener(client_id, request_id, event_queue)

    return EventSourceResponse(event_generator())


@router.post(
    "/tasks/{client_id}/{request_id}/ack",
    responses={404: {"model": ErrorResponse}},
)
async def ack_task(
    client_id: str,
    request_id: str,
    _: str = Depends(verify_token),
):
    """
    결과 수신 확인

    클라이언트가 결과를 성공적으로 수신했음을 알립니다.
    확인된 태스크는 서버에서 삭제됩니다.
    """
    task_manager = get_task_manager()
    success = await task_manager.ack_task(client_id, request_id)

    if not success:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"태스크를 찾을 수 없습니다: {client_id}:{request_id}",
                    "details": {},
                }
            },
        )

    return {"success": True}


@router.post(
    "/tasks/{client_id}/{request_id}/intervene",
    response_model=InterveneResponse,
    status_code=202,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def intervene_task(
    client_id: str,
    request_id: str,
    request: TaskInterveneRequest,
    _: str = Depends(verify_token),
):
    """
    실행 중인 태스크에 개입 메시지 전송

    running 상태의 태스크에만 메시지를 전송할 수 있습니다.
    """
    task_manager = get_task_manager()

    try:
        queue_position = await task_manager.add_intervention(
            client_id=client_id,
            request_id=request_id,
            text=request.text,
            user=request.user,
            attachment_paths=request.attachment_paths,
        )

        return InterveneResponse(
            queued=True,
            queue_position=queue_position,
        )

    except TaskNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "TASK_NOT_FOUND",
                    "message": f"태스크를 찾을 수 없습니다: {client_id}:{request_id}",
                    "details": {},
                }
            },
        )

    except TaskNotRunningError:
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "TASK_NOT_RUNNING",
                    "message": f"태스크가 실행 중이 아닙니다: {client_id}:{request_id}",
                    "details": {},
                }
            },
        )
