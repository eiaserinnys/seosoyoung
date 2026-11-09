"""Kaleidoscope app storage over authenticated MCP."""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any, Callable


class StorageError(RuntimeError):
    pass


class StorageConflict(StorageError):
    pass


class StorageNotFound(StorageError):
    pass


class StorageClient:
    def __init__(self, *, url: str | None = None, token: str | None = None, app_id: str = 'todo'):
        self.url = url if url is not None else os.environ['KALEIDOSCOPE_MCP_URL']
        self._token = token if token is not None else os.environ['KALEIDOSCOPE_MCP_TOKEN']
        self.app_id = app_id
        if not self.url or not self._token:
            raise StorageError('할 일 저장소 주소와 인증 설정을 확인해 주세요.')

    async def read(self, entry_id: str, *, doc: str | None = None) -> dict[str, Any]:
        args = {'app_id': self.app_id, 'entry_id': entry_id}
        if doc is not None:
            args['doc'] = doc
        return await self._call('read_app_storage', args)

    async def write(self, entry_id: str, content: Any, revision: str | None, *, doc: str | None = None) -> dict[str, Any]:
        args = {'app_id': self.app_id, 'entry_id': entry_id, 'content': content}
        if revision is not None:
            args['expected_revision'] = revision
        if doc is not None:
            args['doc'] = doc
        return await self._call('write_app_storage', args)

    async def _call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport

        try:
            transport = StreamableHttpTransport(self.url, headers={'Authorization': f'Bearer {self._token}'})
            async with Client(transport) as client:
                result = await client.call_tool(name, arguments, raise_on_error=False)
        except Exception:
            raise StorageError('할 일 저장소에 연결하지 못했습니다.') from None
        structured = getattr(result, 'structured_content', None) or getattr(result, 'structuredContent', None)
        if structured is None:
            content = getattr(result, 'content', [])
            try:
                structured = json.loads(content[0].text)
            except (IndexError, AttributeError, TypeError, json.JSONDecodeError):
                raise StorageError('할 일 저장소 응답을 읽지 못했습니다.') from None
        if not isinstance(structured, Mapping):
            raise StorageError('할 일 저장소 응답을 읽지 못했습니다.')
        if getattr(result, 'is_error', False) or getattr(result, 'isError', False):
            if structured.get('id') in {'STORAGE_ITEM_WRITE_CONFLICT', 'STORAGE_DOCUMENT_WRITE_CONFLICT', 'STORAGE_APP_VALUE_WRITE_CONFLICT', 'STORAGE_SERVER_WRITE_CONFLICT'}:
                raise StorageConflict('할 일 저장소가 변경됐습니다.')
            if structured.get('id') == 'STORAGE_DOCUMENT_READ_NOT_FOUND':
                raise StorageNotFound('할 일 메모가 없습니다.')
            raise StorageError('할 일 저장소 요청을 처리하지 못했습니다.')
        return dict(structured)


async def update_items(storage, operation: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], bool]:
    """Apply the same intent once more only when the saved revision conflicts."""
    for attempt in range(2):
        current = await storage.read('items')
        items = current['content']
        updated = operation(items)
        if updated == items:
            return items, False
        try:
            await storage.write('items', updated, current.get('revision'))
        except StorageConflict:
            if attempt == 0:
                continue
            raise
        return updated, True
    raise AssertionError('unreachable')
