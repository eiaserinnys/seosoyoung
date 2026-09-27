from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from seosoyoung.slackbot.handlers.lore_search import (
    build_search_blocks,
    judge_lore_search,
    search_lore,
    try_handle_lore_search,
)
from seosoyoung.slackbot.handlers import mention
from seosoyoung.slackbot.config import Config


def _config(**overrides):
    values = {
        "jev_api_key": "jev-test-key",
        "lore_search_url": "https://lore-search.example/",
        "lore_search_api_key": "lore-test-key",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _response(body):
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status.return_value = None
    return response


class TestJevIntentRequest:
    def test_sends_lore_search_question_and_reads_noul_score(self):
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response({"answers": {"lore_search": {"type": "noul", "noul": 0.71}}}),
        ) as post:
            score = judge_lore_search("루카가 왜 떠났는지 찾아줘", "jev-test-key")

        assert score == 0.71
        args, kwargs = post.call_args
        assert args[0] == "https://api.typesafe.ai/v1/systemone"
        assert kwargs["headers"]["Authorization"] == "Bearer jev-test-key"
        assert kwargs["json"]["model"] == "jev-latest"
        state = json.loads(kwargs["json"]["state"])
        assert state["user_prompt"] == "루카가 왜 떠났는지 찾아줘"
        assert "대사 고쳐줘" in state["instructions"]
        assert kwargs["json"]["questions"]["lore_search"]["type"] == "noul"

    def test_rejects_missing_or_out_of_range_score(self):
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response({"answers": {"lore_search": {"type": "noul", "noul": 1.2}}}),
        ):
            with pytest.raises(ValueError):
                judge_lore_search("질의", "jev-test-key")


class TestLoreSearchApiRequest:
    def test_posts_bearer_authenticated_query_and_returns_results(self):
        body = {"query": "루카의 과거", "search_url": "https://lore-search.example", "results": []}
        with patch(
            "seosoyoung.slackbot.handlers.lore_search.requests.post",
            return_value=_response(body),
        ) as post:
            result = search_lore("루카의 과거", "https://lore-search.example/", "lore-test-key")

        assert result == body
        args, kwargs = post.call_args
        assert args[0] == "https://lore-search.example/api/search"
        assert kwargs["headers"]["Authorization"] == "Bearer lore-test-key"
        assert kwargs["json"] == {"query": "루카의 과거"}


class TestLoreSearchRouting:
    @pytest.mark.parametrize("missing", ["jev_api_key", "lore_search_url", "lore_search_api_key"])
    def test_any_missing_environment_value_disables_the_feature(self, missing):
        config = _config(**{missing: ""})
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", config, create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search") as judge:
            handled = try_handle_lore_search(
                "로어를 찾아줘", MagicMock(), client=MagicMock(), channel="C123", thread_ts="thread-1",
            )

        assert handled is False
        judge.assert_not_called()

    def test_score_at_threshold_searches_and_posts_block_kit_to_the_thread(self):
        say = MagicMock()
        say.return_value = {"ts": "placeholder-1"}
        client = MagicMock()
        response = {
            "search_url": "https://lore-search.example",
            "results": [{"title": "루카", "source_type": "lore", "excerpt": "설정 발췌", "path": "lore/luka.yaml"}],
        }
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.7), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", return_value=response) as search:
            handled = try_handle_lore_search(
                "루카 설정 찾아줘", say, client=client, channel="C123", thread_ts="thread-1",
            )

        assert handled is True
        search.assert_called_once_with("루카 설정 찾아줘", "https://lore-search.example/", "lore-test-key")
        say.assert_called_once_with(text=Config.bot.thinking_text, thread_ts="thread-1")
        update = client.chat_update.call_args.kwargs
        assert update["channel"] == "C123"
        assert update["ts"] == "placeholder-1"
        assert update["blocks"][-1]["elements"][0]["url"] == "https://lore-search.example"
        client.chat_delete.assert_not_called()

    def test_score_below_threshold_skips_search(self):
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.69), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore") as search:
            say = MagicMock()
            handled = try_handle_lore_search(
                "대사 고쳐줘", say, client=MagicMock(), channel="C123", thread_ts="thread-1",
            )

        assert handled is False
        search.assert_not_called()
        say.assert_not_called()

    def test_jev_failure_is_logged_and_falls_back(self):
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", side_effect=RuntimeError("secret")), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore") as search, \
             patch("seosoyoung.slackbot.handlers.lore_search.logger") as logger:
            say = MagicMock()
            handled = try_handle_lore_search(
                "질의", say, client=MagicMock(), channel="C123", thread_ts="thread-1",
            )

        assert handled is False
        search.assert_not_called()
        say.assert_not_called()
        logger.warning.assert_called_once()

    def test_search_failure_is_logged_and_falls_back(self):
        say = MagicMock()
        say.return_value = {"ts": "placeholder-2"}
        client = MagicMock()
        with patch("seosoyoung.slackbot.handlers.lore_search.Config.lore_search", _config(), create=True), \
             patch("seosoyoung.slackbot.handlers.lore_search.judge_lore_search", return_value=0.9), \
             patch("seosoyoung.slackbot.handlers.lore_search.search_lore", side_effect=RuntimeError("secret")), \
             patch("seosoyoung.slackbot.handlers.lore_search.logger") as logger:
            handled = try_handle_lore_search(
                "질의", say, client=client, channel="C123", thread_ts="thread-1",
            )

        assert handled is False
        say.assert_called_once_with(text=Config.bot.thinking_text, thread_ts="thread-1")
        client.chat_delete.assert_called_once_with(channel="C123", ts="placeholder-2")
        client.chat_update.assert_not_called()
        logger.warning.assert_called_once()

    def test_result_blocks_have_bounded_section_text_and_a_site_button(self):
        blocks = build_search_blocks({
            "search_url": "https://lore-search.example",
            "results": [{
                "title": "루카",
                "source_type": "shay",
                "excerpt": "대사 <@U123> & 설명",
                "path": "dialogue/luka",
            }],
        })

        assert len(blocks) <= 50
        assert all(len(block.get("text", {}).get("text", "")) <= 3000 for block in blocks)
        assert "&lt;@U123&gt;" in blocks[1]["text"]["text"]
        assert blocks[-1]["elements"][0]["url"] == "https://lore-search.example"


def _register_mention_handler(session_manager):
    dependencies = {
        "session_manager": session_manager,
        "restart_manager": SimpleNamespace(is_pending=False),
        "get_running_session_count": MagicMock(return_value=0),
        "run_claude_in_session": MagicMock(),
        "check_permission": MagicMock(return_value=True),
        "get_user_role": MagicMock(return_value={"username": "tester", "role": "user"}),
        "send_restart_confirmation": MagicMock(),
    }
    registered = {}
    app = MagicMock()

    def capture(event_type):
        def decorator(function):
            registered[event_type] = function
            return function
        return decorator

    app.event = capture
    mention.register_mention_handlers(app, dependencies)
    return registered["app_mention"], dependencies


class TestMentionHandlerIntegration:
    def test_new_thread_mention_can_be_routed_to_lore_search(self):
        session_manager = MagicMock()
        session_manager.get.return_value = None
        handler, _dependencies = _register_mention_handler(session_manager)
        event = {
            "user": "U123",
            "text": "<@BOT> 루카 설정 찾아줘",
            "channel": "C123",
            "ts": "1234567890.000002",
            "thread_ts": "1234567890.000001",
        }
        say = MagicMock()

        client = MagicMock()
        with patch("seosoyoung.slackbot.handlers.mention.try_handle_lore_search", return_value=True) as route, \
             patch("seosoyoung.slackbot.handlers.mention.create_session_and_run_claude") as general:
            handler(event, say, client)

        route.assert_called_once_with(
            "루카 설정 찾아줘", say=say, client=client, channel="C123", thread_ts="1234567890.000001",
        )
        general.assert_not_called()

    def test_existing_session_thread_skips_lore_search(self):
        session_manager = MagicMock()
        session_manager.get.return_value = SimpleNamespace(user_id="U123")
        handler, dependencies = _register_mention_handler(session_manager)
        event = {
            "user": "U123",
            "text": "<@BOT> 루카 설정 찾아줘",
            "channel": "C123",
            "ts": "1234567890.000002",
            "thread_ts": "1234567890.000001",
        }

        with patch("seosoyoung.slackbot.handlers.mention.try_handle_lore_search") as route, \
             patch("seosoyoung.slackbot.handlers.mention.process_thread_message"):
            handler(event, MagicMock(), MagicMock())

        route.assert_not_called()
