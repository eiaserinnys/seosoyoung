"""트렐로 카드 프롬프트 빌더

Config 의존성 없이, list_ids를 생성자에서 직접 받습니다.
"""

from seosoyoung.slackbot.plugins.trello.client import TrelloClient, TrelloCard
from seosoyoung.slackbot.plugins.trello.formatting import format_checklists, format_comments


class PromptBuilder:
    """트렐로 카드용 프롬프트 빌더

    TrelloClient를 통해 카드의 체크리스트, 코멘트 등을 조회하고
    Claude에 전달할 프롬프트 문자열을 생성합니다.
    """

    def __init__(self, trello: TrelloClient, *, list_ids: dict[str, str]):
        """
        Args:
            trello: TrelloClient 인스턴스
            list_ids: 리스트 ID 매핑 (key: 리스트 역할명, value: 리스트 ID)
                예: {"draft": "...", "backlog": "...", "blocked": "...", "review": "..."}
        """
        self.trello = trello
        self._list_ids = list_ids

    def build_card_context(self, card_id: str, desc: str = "") -> str:
        """카드의 체크리스트, 코멘트, 리스트 ID 컨텍스트를 조합"""
        checklists = self.trello.get_card_checklists(card_id)
        checklists_text = format_checklists(checklists)

        comments = self.trello.get_card_comments(card_id)
        comments_text = format_comments(comments)

        list_ids_text = self._build_list_ids_context()

        return f"""
## 카드 본문
{desc if desc else "(본문 없음)"}

## 체크리스트
{checklists_text}

## 코멘트
{comments_text}
{list_ids_text}"""

    def build_to_go(self, card: TrelloCard, has_execute: bool = False) -> str:
        """To Go 카드용 프롬프트 생성"""
        card_context = self.build_card_context(card.id, card.desc)
        auto_move_notice = "**카드는 이미 워처에 의해 🔨 In Progress로 이동되었습니다. 카드를 In Progress로 이동하지 마세요.**"

        if has_execute:
            return f"""🚀 To Go 리스트에 들어온 '{card.name}' 태스크를 실행해주세요.

{auto_move_notice}

카드 ID: {card.id}
카드 URL: {card.url}
{_build_task_context_hint()}
{card_context}"""
        else:
            return f"""📋 To Go 리스트에 들어온 '{card.name}' 태스크의 계획을 수립해주세요.

{auto_move_notice}
**Execute 레이블이 없으므로 계획 수립만 진행합니다.**

1. 카드를 분석하고 계획을 수립하세요
2. 체크리스트로 세부 단계를 기록하세요
3. 완료 후 카드를 📦 Backlog로 이동하세요
4. 사용자가 Execute 레이블을 붙이고 다시 🚀 To Go로 보내면 실행됩니다

카드 ID: {card.id}
카드 URL: {card.url}
{_build_task_context_hint()}
{card_context}"""

    def build_reaction_execute(self, info) -> str:
        """리액션 기반 실행용 프롬프트 생성"""
        card = self.trello.get_card(info.card_id)
        desc = card.desc if card else ""

        card_context = self.build_card_context(info.card_id, desc)

        return f"""🚀 리액션으로 실행이 요청된 '{info.card_name}' 태스크를 실행해주세요.

**카드는 이미 워처에 의해 🔨 In Progress로 이동되었습니다. 카드를 In Progress로 이동하지 마세요.**

이전에 계획 수립이 완료된 태스크입니다.
체크리스트와 코멘트를 확인하고 계획에 따라 작업을 수행하세요.

카드 ID: {info.card_id}
카드 URL: {info.card_url}
{_build_task_context_hint()}
{card_context}"""

    def build_list_run(
        self,
        card: TrelloCard,
        session_id: str,
        current: int,
        total: int,
    ) -> str:
        """리스트 정주행용 프롬프트 생성"""
        card_context = self.build_card_context(card.id, card.desc)

        return f"""📋 리스트 정주행 [{current}/{total}]

**정주행 세션 ID**: `{session_id}`
**카드**: {card.name}
**카드 ID**: {card.id}
**카드 URL**: {card.url}

이 카드의 작업을 수행해주세요. 체크리스트와 코멘트를 확인하고 계획에 따라 작업하세요.
{_build_task_context_hint()}
{card_context}"""

    def _build_list_ids_context(self) -> str:
        """자주 사용하는 리스트 ID 컨텍스트 생성"""
        label_map = {
            "draft": "📥 Draft",
            "backlog": "📦 Backlog",
            "blocked": "🚧 Blocked",
            "review": "👀 Review",
        }
        lines = ["## 리스트 ID (MCP 검색 불필요)"]
        for key, label in label_map.items():
            list_id = self._list_ids.get(key)
            if list_id:
                lines.append(f"- {label}: {list_id}")

        return "\n".join(lines) + "\n"


def _build_task_context_hint() -> str:
    """태스크 컨텍스트 힌트 생성"""
    return """
태스크는 여러가지 이유로 중단되거나 재개될 수 있습니다.
아래 체크리스트와 코멘트를 참고하세요.
"""
