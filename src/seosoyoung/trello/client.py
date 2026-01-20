"""Trello API 클라이언트"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import requests

from seosoyoung.config import Config

logger = logging.getLogger(__name__)

TRELLO_API_BASE = "https://api.trello.com/1"


@dataclass
class TrelloCard:
    """트렐로 카드 정보"""
    id: str
    name: str
    desc: str
    url: str
    list_id: str
    list_name: str = ""
    due_complete: bool = False
    labels: list = field(default_factory=list)  # [{"id": "...", "name": "...", "color": "..."}]


class TrelloClient:
    """Trello API 클라이언트"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        token: Optional[str] = None,
        board_id: Optional[str] = None,
    ):
        self.api_key = api_key or Config.TRELLO_API_KEY
        self.token = token or Config.TRELLO_TOKEN
        self.board_id = board_id or Config.TRELLO_BOARD_ID

        if not self.api_key or not self.token:
            logger.warning("Trello API 키 또는 토큰이 설정되지 않았습니다.")

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict | list]:
        """API 요청"""
        url = f"{TRELLO_API_BASE}{endpoint}"
        params = kwargs.pop("params", {})
        params["key"] = self.api_key
        params["token"] = self.token

        try:
            response = requests.request(method, url, params=params, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Trello API 요청 실패: {e}")
            return None

    def get_cards_in_list(self, list_id: str) -> list[TrelloCard]:
        """특정 리스트의 카드 목록 조회"""
        data = self._request("GET", f"/lists/{list_id}/cards")
        if not data:
            return []

        cards = []
        for card_data in data:
            cards.append(TrelloCard(
                id=card_data["id"],
                name=card_data["name"],
                desc=card_data.get("desc", ""),
                url=card_data.get("shortUrl", ""),
                list_id=list_id,
                due_complete=card_data.get("dueComplete", False),
                labels=card_data.get("labels", []),
            ))
        return cards

    def get_card(self, card_id: str) -> Optional[TrelloCard]:
        """카드 상세 조회"""
        data = self._request("GET", f"/cards/{card_id}")
        if not data:
            return None

        return TrelloCard(
            id=data["id"],
            name=data["name"],
            desc=data.get("desc", ""),
            url=data.get("shortUrl", ""),
            list_id=data.get("idList", ""),
            labels=data.get("labels", []),
        )

    def update_card_name(self, card_id: str, name: str) -> bool:
        """카드 제목 변경

        Args:
            card_id: 카드 ID
            name: 새 제목

        Returns:
            성공 여부
        """
        result = self._request("PUT", f"/cards/{card_id}", params={"name": name})
        return result is not None

    def move_card(self, card_id: str, list_id: str) -> bool:
        """카드를 다른 리스트로 이동

        Args:
            card_id: 카드 ID
            list_id: 대상 리스트 ID

        Returns:
            성공 여부
        """
        result = self._request("PUT", f"/cards/{card_id}", params={"idList": list_id})
        return result is not None

    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        return bool(self.api_key and self.token)
