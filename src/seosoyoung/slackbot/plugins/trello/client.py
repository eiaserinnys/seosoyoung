"""Trello API 클라이언트

Config 의존성 없이, 생성자에서 api_key/token/board_id를 직접 받습니다.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import requests

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
    labels: list = field(default_factory=list)


class TrelloClient:
    """Trello API 클라이언트

    모든 설정은 생성자에서 직접 전달받습니다.
    Config 싱글턴에 의존하지 않습니다.
    """

    def __init__(self, *, api_key: str, token: str, board_id: str):
        self.api_key = api_key
        self.token = token
        self.board_id = board_id

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
        """카드 제목 변경"""
        result = self._request("PUT", f"/cards/{card_id}", params={"name": name})
        return result is not None

    def move_card(self, card_id: str, list_id: str) -> bool:
        """카드를 다른 리스트로 이동"""
        result = self._request("PUT", f"/cards/{card_id}", params={"idList": list_id})
        return result is not None

    def get_card_checklists(self, card_id: str) -> list[dict]:
        """카드의 체크리스트 목록 조회"""
        data = self._request("GET", f"/cards/{card_id}/checklists")
        if not data:
            return []

        checklists = []
        for checklist in data:
            items = []
            for item in checklist.get("checkItems", []):
                items.append({
                    "id": item["id"],
                    "name": item["name"],
                    "state": item["state"],
                })
            checklists.append({
                "id": checklist["id"],
                "name": checklist["name"],
                "items": items,
            })
        return checklists

    def get_card_comments(self, card_id: str, limit: int = 50) -> list[dict]:
        """카드의 코멘트 목록 조회"""
        data = self._request(
            "GET",
            f"/cards/{card_id}/actions",
            params={"filter": "commentCard", "limit": limit}
        )
        if not data:
            return []

        comments = []
        for action in data:
            if action.get("type") == "commentCard":
                comments.append({
                    "id": action["id"],
                    "text": action.get("data", {}).get("text", ""),
                    "date": action.get("date", ""),
                    "author": action.get("memberCreator", {}).get("fullName", "Unknown"),
                })
        return comments

    def get_lists(self) -> list[dict]:
        """보드의 리스트 목록 조회"""
        data = self._request("GET", f"/boards/{self.board_id}/lists")
        if not data:
            return []

        return [
            {"id": lst["id"], "name": lst["name"]}
            for lst in data
        ]

    def remove_label_from_card(self, card_id: str, label_id: str) -> bool:
        """카드에서 레이블 제거"""
        result = self._request("DELETE", f"/cards/{card_id}/idLabels/{label_id}")
        return result is not None

    def is_configured(self) -> bool:
        """API 설정 여부 확인"""
        return bool(self.api_key and self.token)
