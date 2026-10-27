"""FastMCP access to the personal Atom card API used by daily TODOs."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

ATOM_MCP_URL = "https://atom.eiaserinnys.me/mcp"


class AtomMcpClient:
    def __init__(self, api_key: str | None = None, *, url: str = ATOM_MCP_URL):
        self.api_key = api_key if api_key is not None else os.environ["ATOM_AGENT_KEY"]
        self.url = url

    async def get_card(self, card_id: str) -> dict[str, Any]:
        result = await self._call("get_card", {"card_id": card_id})
        card = _as_mapping(result)
        if "card" in card and isinstance(card["card"], Mapping):
            card = dict(card["card"])
        if not isinstance(card.get("content"), str) or not isinstance(card.get("version"), int):
            raise ValueError("Atom get_card returned an incomplete card")
        return card

    async def update_card(
        self, card_id: str, *, content: str, expected_version: int
    ) -> dict[str, Any]:
        result = await self._call(
            "update_card",
            {"card_id": card_id, "content": content, "expected_version": expected_version},
        )
        return _as_mapping(result)

    async def search_cards(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        result = await self._call("search_cards", {"query": query, "limit": limit})
        if isinstance(result, list):
            return [dict(card) for card in result if isinstance(card, Mapping)]
        value = _as_mapping(result)
        cards = value.get("cards", value.get("results", []))
        return [dict(card) for card in cards if isinstance(card, Mapping)]

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        from fastmcp import Client
        from fastmcp.client.transports import StreamableHttpTransport

        transport = StreamableHttpTransport(
            self.url,
            headers={"x-api-key": self.api_key},
        )
        async with Client(transport) as client:
            result = await client.call_tool(name, arguments)
        if getattr(result, "isError", False):
            message = "Atom MCP request failed"
            content = getattr(result, "content", [])
            if content:
                message = getattr(content[0], "text", message)
            raise RuntimeError(message)
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured
        content = getattr(result, "content", [])
        if content and getattr(content[0], "text", None):
            raw = content[0].text
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        return result


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list):
        if len(value) == 1:
            return _as_mapping(value[0])
        raise ValueError("Atom MCP returned multiple content values")
    if isinstance(value, str):
        parsed = json.loads(value)
        return _as_mapping(parsed)
    if hasattr(value, "model_dump"):
        return _as_mapping(value.model_dump())
    raise ValueError("Atom MCP returned an unexpected response")
