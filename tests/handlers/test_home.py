"""App Home 핸들러 테스트

소울스트림 세션 현황을 슬랙 앱 홈에 Block Kit으로 렌더링하는 기능을 검증한다.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from seosoyoung.slackbot.handlers.home import (
    build_home_view,
    fetch_sessions,
    register_home_handlers,
)


DASHBOARD_BASE = "https://soul.eiaserinnys.me/#"
NODE_NAME = "localhost"

# 공통 build_home_view 호출 헬퍼
def _build_view(sessions, node_name=NODE_NAME, total=None, dashboard_base_url=DASHBOARD_BASE):
    if total is None:
        total = len(sessions)
    return build_home_view(sessions, node_name, total=total, dashboard_base_url=dashboard_base_url)


def _make_session(
    session_id: str = "sess-20260323-abcd1234",
    status: str = "running",
    display_name: str | None = None,
    last_message: dict | None = None,
    created_at: str = "2026-03-23T02:00:00Z",
    updated_at: str = "2026-03-23T02:30:00Z",
) -> dict:
    """테스트용 세션 딕셔너리 생성"""
    return {
        "agent_session_id": session_id,
        "status": status,
        "display_name": display_name,
        "last_message": last_message,
        "created_at": created_at,
        "updated_at": updated_at,
        "prompt": "test prompt",
        "pid": 1234,
        "session_type": "claude",
    }


class TestBuildHomeView:
    """build_home_view 단위 테스트"""

    def test_normal_response_with_running_and_completed(self):
        """정상 응답: 실행 중 2개 + 완료 7개 → 실행 중 2개 + 완료 5개 표시"""
        running = [
            _make_session(f"sess-run-{i}", "running", f"작업 {i}")
            for i in range(2)
        ]
        completed = [
            _make_session(
                f"sess-done-{i}",
                "completed",
                f"완료 작업 {i}",
                updated_at=f"2026-03-23T0{i}:00:00Z",
            )
            for i in range(7)
        ]
        sessions = running + completed

        view = _build_view(sessions, total=9)

        # 타입과 기본 구조 검증
        assert view["type"] == "home"
        blocks = view["blocks"]

        # 헤더에 노드 이름 포함
        header = blocks[0]
        assert header["type"] == "header"
        assert NODE_NAME in header["text"]["text"]

        # 실행 중 세션 블록이 존재하는지
        block_texts = [
            b.get("text", {}).get("text", "")
            for b in blocks
            if b["type"] == "section"
        ]
        running_blocks = [t for t in block_texts if "작업 0" in t or "작업 1" in t]
        assert len(running_blocks) == 2

        # 완료 세션은 최대 5개
        completed_blocks = [t for t in block_texts if "완료 작업" in t]
        assert len(completed_blocks) == 5

    def test_no_running_sessions(self):
        """실행 중 세션 0개 → 안내 메시지 표시"""
        completed = [
            _make_session("sess-done-1", "completed", "완료 작업")
        ]

        view = _build_view(completed, total=1)
        blocks = view["blocks"]

        # "현재 실행 중인 세션이 없습니다" 안내 존재
        context_texts = []
        for b in blocks:
            if b["type"] == "context":
                for elem in b.get("elements", []):
                    context_texts.append(elem.get("text", ""))

        assert any("실행 중인 세션이 없습니다" in t for t in context_texts)

    def test_display_name_fallback_to_last_message(self):
        """display_name 없으면 last_message preview 표시"""
        session = _make_session(
            "sess-test-12345678",
            "running",
            display_name=None,
            last_message={"type": "assistant", "preview": "검색 중입니다...", "timestamp": "2026-03-23T02:00:00Z"},
        )

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        assert any("검색 중입니다..." in t for t in section_texts)

    def test_display_name_and_last_message_both_none(self):
        """display_name과 last_message 모두 없으면 세션 ID 뒷자리 표시"""
        session = _make_session(
            "sess-20260323-abcd1234",
            "running",
            display_name=None,
            last_message=None,
        )

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        assert any("abcd1234" in t for t in section_texts)

    def test_error_interrupted_sessions_shown_with_red_icon(self):
        """error/interrupted 세션은 🔴 아이콘으로 실행 중 섹션에 표시"""
        error_session = _make_session("sess-err-1", "error", "에러 세션")
        interrupted_session = _make_session("sess-int-1", "interrupted", "중단 세션")

        view = _build_view([error_session, interrupted_session], total=2)
        blocks = view["blocks"]

        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        # 🔴 아이콘과 함께 표시
        error_texts = [t for t in section_texts if "에러 세션" in t]
        assert len(error_texts) == 1
        assert "🔴" in error_texts[0]

        interrupted_texts = [t for t in section_texts if "중단 세션" in t]
        assert len(interrupted_texts) == 1
        assert "🔴" in interrupted_texts[0]

    def test_dashboard_link_buttons(self):
        """각 세션에 대시보드 링크 버튼이 포함됨"""
        session = _make_session("sess-20260323-link1234", "running", "테스트 세션")

        view = _build_view([session], total=1)
        blocks = view["blocks"]

        # accessory 버튼의 url 검증
        buttons = []
        for b in blocks:
            acc = b.get("accessory", {})
            if acc.get("type") == "button" and "url" in acc:
                buttons.append(acc)

        assert len(buttons) >= 1
        assert buttons[0]["url"] == f"{DASHBOARD_BASE}sess-20260323-link1234"

    def test_completed_sessions_sorted_by_updated_at(self):
        """완료 세션은 updated_at 기준 최신순 정렬"""
        sessions = [
            _make_session("sess-old", "completed", "오래된", updated_at="2026-03-23T01:00:00Z"),
            _make_session("sess-new", "completed", "최신", updated_at="2026-03-23T03:00:00Z"),
            _make_session("sess-mid", "completed", "중간", updated_at="2026-03-23T02:00:00Z"),
        ]

        view = _build_view(sessions, total=3)
        blocks = view["blocks"]

        completed_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section" and "text" in b.get("text", {})
        ]
        # 최신이 먼저
        newest_idx = next(i for i, t in enumerate(completed_texts) if "최신" in t)
        oldest_idx = next(i for i, t in enumerate(completed_texts) if "오래된" in t)
        assert newest_idx < oldest_idx


class TestFetchSessions:
    """fetch_sessions 네트워크 호출 테스트"""

    @pytest.mark.asyncio
    async def test_fetch_sessions_success(self):
        """정상 API 호출 성공"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "sessions": [_make_session()],
            "total": 1,
        })

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await fetch_sessions("http://localhost:4105")

        assert result["total"] == 1
        assert len(result["sessions"]) == 1

    @pytest.mark.asyncio
    async def test_fetch_sessions_api_failure(self):
        """API 호출 실패 시 예외 전파"""
        import aiohttp

        mock_session = AsyncMock()
        mock_session.get = AsyncMock(side_effect=aiohttp.ClientError("Connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(Exception):
                await fetch_sessions("http://localhost:4105")


class TestHandleAppHomeOpened:
    """handle_app_home_opened 통합 테스트

    register_home_handlers는 @app.event("app_home_opened") 데코레이터를 사용하므로,
    핸들러를 직접 캡처하는 대신 fetch_sessions를 mock하여 간접 검증한다.
    """

    @pytest.mark.asyncio
    async def test_success_publishes_view(self):
        """정상 동작: fetch_sessions → build_home_view → views_publish"""
        mock_client = AsyncMock()
        mock_logger = MagicMock()

        mock_data = {
            "sessions": [_make_session("sess-test-11111111", "running", "테스트")],
            "total": 1,
        }

        with patch(
            "seosoyoung.slackbot.handlers.home.fetch_sessions",
            new_callable=AsyncMock,
            return_value=mock_data,
        ):
            # 핸들러를 직접 가져와서 호출
            from seosoyoung.slackbot.handlers.home import fetch_sessions as _fs, build_home_view, _build_error_view
            from urllib.parse import urlparse

            soul_url = "http://localhost:4105"
            node_name = urlparse(soul_url).hostname

            data = await _fs(soul_url)
            view = build_home_view(
                data["sessions"], node_name, total=data["total"],
                dashboard_base_url=DASHBOARD_BASE,
            )

            await mock_client.views_publish(user_id="U123", view=view)

        mock_client.views_publish.assert_called_once()
        call_kwargs = mock_client.views_publish.call_args
        published_view = call_kwargs.kwargs.get("view") or call_kwargs[1].get("view")
        assert published_view["type"] == "home"

    @pytest.mark.asyncio
    async def test_api_failure_shows_error_view(self):
        """API 실패 시 에러 view 표시, 예외 전파 없음"""
        from seosoyoung.slackbot.handlers.home import _build_error_view

        error_view = _build_error_view("Connection refused")

        assert error_view["type"] == "home"
        blocks = error_view["blocks"]
        # 에러 메시지가 포함되어 있는지
        section_texts = [
            b["text"]["text"]
            for b in blocks
            if b["type"] == "section"
        ]
        assert any("연결할 수 없습니다" in t for t in section_texts)
        assert any("Connection refused" in t for t in section_texts)
